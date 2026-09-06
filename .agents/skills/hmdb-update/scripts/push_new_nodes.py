#!/usr/bin/env python
"""Create OSM nodes for every atlas row that is linked to hmdb but not yet mapped.

    python .claude/skills/hmdb-update/scripts/push_new_nodes.py \
        --extract scripts/tmp/overpass_tx_plaques_YYYYMMDD.json \
        [--adopt THC=NODEID ...] [--only THC,...] [--atlas atlas_db.csv] \
        [--state scripts/tmp/push_new_nodes_YYYYMMDD.state.json] [--dry-run | --stamp-only]

Candidate mask (the only "ready to push" set, see memory): isHMDB=True and
isOSM=False and isActive!=False and isMissing!=True and isPending!=True, with a
verified:* coordinate (hmdb field position). Rows without a ref:US-TX:thc get
the `note=Marker is not present in THC Atlas database` tag like node/6215298453.

Dedup is offline against a fresh statewide memorial=plaque extract
(fetch_plaque_extract.sh) on four keys: ref:US-TX:thc, ref:hmdb, the THC id in
website/source:website (Details/<10 digits> -> int(digits[4:])), and name
similarity >= 0.8 within 250 m. Any hit aborts unless that thc# is listed in
--adopt, in which case the existing node is *modified* (refs, address, operator
added; the mapper's name/inscription/material/geometry kept) and the atlas takes
its id. Immediately before writing, a live Overpass query re-checks that no
Texas node holds any ref about to be written, and validate_ref_plan() runs on
the produced state for both ref tags.

Changesets: <= --max-batch nodes each, grouped by county (large counties split,
small ones merged into "A, B and C counties" batches), --pause seconds apart,
bot=no. Guardrails: float-format assert on every tag, comment <= 255 chars,
resumable state file keyed on "thc|hmdb", live re-fetch of every node before the
atlas is stamped (isOSM=True + OsmNodeID; DATA_NOTE on adoptions). Atlas is
backed up to scripts/tmp/ and written with newline='' + lineterminator='\\n'.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "pythonLib"))
from thc_toolkit.atlas_check import assert_no_float_formatted_tags  # noqa: E402
from thc_toolkit.osm_dedup import haversine_m, name_similarity  # noqa: E402
from thc_toolkit.osm_refix_direct import (  # noqa: E402
    RefPlanError, _xe, build_osmchange, close_changeset, fetch_nodes_bulk, make_session,
    open_changeset, read_josm_oauth_token, upload_diff, validate_ref_plan)

ENDPOINTS = ("https://overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter")
TX_BBOX = "25.8,-106.7,36.6,-93.4"
ADDR_COLS = ("addr:full", "addr:city", "addr:county")
LINK_COLS = ("wikimedia_commons", "subject:wikimedia_commons", "subject:wikipedia", "subject:wikidata")
UA = "thc-toolkit/0.1 (joelotz@gmail.com)"


def is_true(v: str) -> bool:
    return (v or "").strip() == "True"


def row_key(r: dict) -> str:
    return f"{r['ref:US-TX:thc'].strip()}|{r['ref:hmdb'].strip()}"


def v(row: dict, col: str) -> str | None:
    s = (row.get(col) or "").strip()
    return s or None


def load_atlas(p: Path) -> tuple[list[dict], list[str]]:
    with p.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames)


def candidates(rows: list[dict], only: set[str] | None) -> list[dict]:
    out = []
    for r in rows:
        if not (is_true(r["isHMDB"]) and not is_true(r["isOSM"]) and r["isActive"].strip() != "False"
                and not is_true(r["isMissing"]) and not is_true(r["isPending"])):
            continue
        if only and r["ref:US-TX:thc"].strip() not in only:
            continue
        if not r["verified:Latitude"].strip() or not r["verified:Longitude"].strip():
            raise SystemExit(f"candidate without verified coord: {row_key(r)} {r['name']!r}")
        out.append(r)
    return out


def atlas_tags(row: dict) -> dict[str, str]:
    tags = {"historic": "memorial", "memorial": "plaque", "operator": "Texas Historical Commission",
            "operator:wikidata": "Q2397965", "name": row["name"].strip()}
    thc = v(row, "ref:US-TX:thc")
    if thc:
        tags["ref:US-TX:thc"] = thc
    else:
        tags["note"] = "Marker is not present in THC Atlas database"
    for col in ("ref:hmdb", "memorial:website", "website", "start_date", "thc:designation", *ADDR_COLS, *LINK_COLS):
        val = v(row, col)
        if val:
            tags[col] = val
    if tags.get("addr:county", "").endswith(" County"):
        tags["addr:county"] = tags["addr:county"][: -len(" County")]
    assert_no_float_formatted_tags(tags)
    return tags


def adoption_tags(live_tags: dict, row: dict) -> dict[str, str]:
    """Add what the atlas knows; never touch name, inscription, material, ref, addr:postcode/state or geometry."""
    t = dict(live_tags)
    want = atlas_tags(row)
    if t.get("website", "").endswith("/print") and "source:website" not in t:
        t["source:website"] = t["website"]
    for k, val in want.items():
        if k == "name":
            continue
        if k not in t:
            t[k] = val
        elif k in ("ref:hmdb", "memorial:website", "website", "ref:US-TX:thc", "start_date", *ADDR_COLS) and t[k] != val:
            t[k] = val
    assert_no_float_formatted_tags(t)
    return t


def overpass(q: str) -> dict:
    last = None
    for _ in range(2):
        for ep in ENDPOINTS:
            try:
                r = requests.post(ep, data={"data": q}, timeout=150, headers={"User-Agent": UA})
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"   [overpass] {ep}: {e}")
                time.sleep(3)
    raise SystemExit(f"overpass unavailable: {last}")


def live_ref_holders(thcs: list[str], hmdbs: list[str]) -> dict[int, dict]:
    parts = []
    if thcs:
        parts.append(f'  node["ref:US-TX:thc"~"^({"|".join(map(re.escape, thcs))})$"];')
    if hmdbs:
        parts.append(f'  node["ref:hmdb"~"^({"|".join(map(re.escape, hmdbs))})$"];')
    q = f"[out:json][timeout:120][bbox:{TX_BBOX}];\n(\n" + "\n".join(parts) + "\n);\nout tags;"
    return {e["id"]: e.get("tags", {}) for e in overpass(q)["elements"] if e["type"] == "node"}


def offline_dedup(cands: list[dict], extract: Path, adopt: dict[str, int]) -> None:
    nodes = json.load(extract.open())["elements"]
    by_thc: dict[str, list] = {}
    by_hmdb: dict[str, list] = {}
    by_site: dict[str, list] = {}
    for n in nodes:
        tg = n.get("tags", {})
        if tg.get("ref:US-TX:thc"):
            by_thc.setdefault(tg["ref:US-TX:thc"].strip(), []).append(n)
        if tg.get("ref:hmdb"):
            by_hmdb.setdefault(tg["ref:hmdb"].strip(), []).append(n)
        for k in ("website", "source:website"):
            m = re.search(r"Details/(\d{10})", tg.get(k, ""))
            if m:
                by_site.setdefault(str(int(m.group(1)[4:])), []).append(n)
    print(f"[DEDUP] {len(cands)} candidates vs {len(nodes)} plaque nodes in {extract.name}")
    unresolved = []
    for r in cands:
        thc, hm = r["ref:US-TX:thc"].strip(), r["ref:hmdb"].strip()
        lat, lon = float(r["verified:Latitude"]), float(r["verified:Longitude"])
        hits = []
        for lbl, d, key in (("ref:US-TX:thc", by_thc, thc), ("ref:hmdb", by_hmdb, hm), ("website-id", by_site, thc)):
            for n in (d.get(key, []) if key else []):
                hits.append((n, f"{lbl} on n{n['id']} {n['tags'].get('name')!r} {haversine_m(lat, lon, n['lat'], n['lon']):.0f} m"))
        for n in nodes:
            if abs(n["lat"] - lat) > 0.003 or abs(n["lon"] - lon) > 0.003:
                continue
            dm = haversine_m(lat, lon, n["lat"], n["lon"])
            sim = name_similarity(r["name"], n["tags"].get("name", ""))
            if dm <= 250 and sim >= 0.8:
                hits.append((n, f"name {sim:.2f} n{n['id']} {n['tags'].get('name')!r} thc={n['tags'].get('ref:US-TX:thc')} {dm:.0f} m"))
        if not hits:
            continue
        node_ids = {n["id"] for n, _ in hits}
        if thc in adopt and node_ids == {adopt[thc]}:
            print(f"   adopt  thc#{thc} {r['name'][:35]!r} -> n{adopt[thc]}: " + "; ".join(h for _, h in hits))
            continue
        unresolved.append(f"   DUP?  thc#{thc or '-'} hmdb {hm} {r['name'][:35]!r}: " + "; ".join(h for _, h in hits))
    if unresolved:
        print("\n".join(unresolved))
        raise SystemExit("[ABORT] dedup hits above; decide per row (--adopt THC=NODE for a node that is ours, "
                         "hmdb_ignore/DATA_NOTE otherwise) and re-run")
    print("   no unresolved matches")


def plan_batches(cands: list[dict], max_batch: int) -> list[tuple[str, str, list[dict]]]:
    by_county: dict[str, list[dict]] = {}
    for r in cands:
        by_county.setdefault(re.sub(r"\s+County$", "", r["addr:county"].strip()) or "unknown", []).append(r)
    batches: list[tuple[str, str, list[dict]]] = []
    small: list[tuple[str, list[dict]]] = []
    for county in sorted(by_county, key=lambda c: (-len(by_county[c]), c)):
        rows = sorted(by_county[county], key=lambda r: r["name"].lower())
        if len(rows) > max_batch:
            n = -(-len(rows) // max_batch)
            size = -(-len(rows) // n)
            for i in range(n):
                batches.append((county, f" ({i + 1} of {n})", rows[i * size:(i + 1) * size]))
        elif len(rows) >= max_batch // 2:
            batches.append((county, "", rows))
        else:
            small.append((county, rows))
    group: list[tuple[str, list[dict]]] = []
    count = 0
    for county, rows in small:
        if group and count + len(rows) > max_batch:
            batches.append((label_for([c for c, _ in group]), "", [r for _, rs in group for r in rs]))
            group, count = [], 0
        group.append((county, rows))
        count += len(rows)
    if group:
        batches.append((label_for([c for c, _ in group]), "", [r for _, rs in group for r in rs]))
    for label, part, rows in batches:
        assert 0 < len(rows) <= max_batch, (label, part, len(rows))
    return batches


def label_for(counties: list[str]) -> str:
    return counties[0] if len(counties) == 1 else ", ".join(counties[:-1]) + " and " + counties[-1]


def changeset_tags(n: int, label: str, part: str = "") -> dict:
    plural = "counties" if ("," in label or " and " in label) else "County"
    comment = (f"Add {n} Texas Historical Commission marker nodes in {label} {plural}, Texas{part}, at hmdb.org "
               "field-verified positions. Source: atlas.thc.texas.gov + hmdb.org")
    if len(comment) > 255:
        raise SystemExit(f"changeset comment {len(comment)} chars (cap 255): {comment}")
    return {"created_by": "thc-toolkit/0.1", "comment": comment, "source": "atlas.thc.texas.gov; hmdb.org", "bot": "no"}


def build_create_osmchange(ops: list[dict], cs_id: int) -> bytes:
    parts = ['<osmChange version="0.6" generator="thc-toolkit"><create>']
    for op in ops:
        assert_no_float_formatted_tags(op["tags"])
        parts.append(f'<node id="{op["tmp_id"]}" version="1" changeset="{cs_id}" lat="{op["lat"]}" lon="{op["lon"]}">')
        parts += [f'<tag k="{_xe(k)}" v="{_xe(val)}"/>' for k, val in op["tags"].items()]
        parts.append("</node>")
    parts.append("</create></osmChange>")
    return "".join(parts).encode()


def parse_new_ids(diff_xml: str) -> dict[int, int]:
    return {int(c.get("old_id")): int(c.get("new_id")) for c in ET.fromstring(diff_xml) if c.tag == "node"}


def write_atlas(atlas: Path, assignments: dict[str, int], adopted: dict[str, str]) -> None:
    rows, fields = load_atlas(atlas)
    stamped = 0
    for r in rows:
        nid = assignments.get(row_key(r))
        if nid is None:
            continue
        r["isOSM"] = "True"
        r["OsmNodeID"] = str(nid)
        stamped += 1
        if row_key(r) in adopted:
            r["DATA_NOTE"] = (r["DATA_NOTE"].strip() + " | " if r["DATA_NOTE"].strip() else "") + adopted[row_key(r)]
    if stamped != len(assignments):
        raise SystemExit(f"expected to stamp {len(assignments)} rows, stamped {stamped}")
    bak = ROOT / "scripts/tmp" / f"atlas_db.csv.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(atlas, bak)
    with atlas.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] atlas: {stamped} rows stamped isOSM=True + OsmNodeID  (backup {bak.name})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--atlas", type=Path, default=ROOT / "atlas_db.csv")
    ap.add_argument("--extract", type=Path, help="statewide memorial=plaque extract JSON (fetch_plaque_extract.sh)")
    ap.add_argument("--skip-dedup", action="store_true", help="only with a freshly reviewed --only list")
    ap.add_argument("--adopt", action="append", default=[], metavar="THC=NODEID",
                    help="existing node to modify instead of creating (repeatable)")
    ap.add_argument("--only", default=None, help="comma-separated thc#s to restrict the candidate set")
    ap.add_argument("--state", type=Path, default=None)
    ap.add_argument("--max-batch", type=int, default=15)
    ap.add_argument("--pause", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stamp-only", action="store_true", help="skip pushing; verify state-file nodes live and stamp")
    a = ap.parse_args()
    if (ROOT / ".~lock.atlas_db.csv#").exists():
        raise SystemExit("Calc has atlas_db.csv open; close it first")
    if not a.extract and not a.skip_dedup:
        raise SystemExit("pass --extract (fresh fetch_plaque_extract.sh output) or --skip-dedup")
    adopt = {}
    for spec in a.adopt:
        thc, nid = spec.split("=", 1)
        adopt[thc.strip()] = int(nid)
    state_p = a.state or ROOT / "scripts/tmp" / f"push_new_nodes_{date.today():%Y%m%d}.state.json"
    only = {s.strip() for s in a.only.split(",")} if a.only else None

    rows, _ = load_atlas(a.atlas)
    cands = candidates(rows, only)
    print(f"candidates (isHMDB & !isOSM & active & !missing & !pending{' & --only' if only else ''}): {len(cands)}")
    if not cands:
        print("nothing to do")
        return
    if a.extract and not a.skip_dedup:
        offline_dedup(cands, a.extract, adopt)
    adopt_rows = [r for r in cands if r["ref:US-TX:thc"].strip() in adopt]
    missing_adopt = set(adopt) - {r["ref:US-TX:thc"].strip() for r in adopt_rows}
    if missing_adopt:
        raise SystemExit(f"--adopt thc#s not among candidates: {sorted(missing_adopt)}")
    to_create = [r for r in cands if r["ref:US-TX:thc"].strip() not in adopt]

    state = json.loads(state_p.read_text()) if state_p.exists() else {"changesets": [], "assignments": {}, "adopted": {}}
    done = state["assignments"]
    pending = [r for r in to_create if row_key(r) not in done]
    pending_adopt = [r for r in adopt_rows if row_key(r) not in done]
    print(f"to create: {len(to_create)} ({len(pending)} pending)   to adopt: {len(adopt_rows)} ({len(pending_adopt)} pending)   state: {state_p.name}")
    batches = plan_batches(pending, a.max_batch)
    for label, part, brows in batches:
        print(f"  batch {label}{part}: {len(brows)}")

    session = make_session(read_josm_oauth_token())
    adopt_updates = []
    if pending_adopt:
        live = fetch_nodes_bulk([adopt[r["ref:US-TX:thc"].strip()] for r in pending_adopt], session)
        for r in pending_adopt:
            nid = adopt[r["ref:US-TX:thc"].strip()]
            n = live[nid]
            for tag in ("ref:US-TX:thc", "ref:hmdb"):
                if n["tags"].get(tag) not in (None, r[tag].strip()):
                    raise SystemExit(f"n{nid} already carries {tag}={n['tags'][tag]!r}; not an adoption")
            dist = haversine_m(float(r["verified:Latitude"]), float(r["verified:Longitude"]), n["lat"], n["lon"])
            new_tags = adoption_tags(n["tags"], r)
            print(f"\n[ADOPT] n{nid} v{n['version']} {n['tags'].get('name')!r} ({dist:.0f} m from the hmdb coordinate):")
            for k in new_tags:
                if n["tags"].get(k) != new_tags[k]:
                    print(f"     {k}: {n['tags'].get(k)!r} -> {new_tags[k]!r}")
            adopt_updates.append({"node_id": nid, "version": n["version"], "lat": n["lat"], "lon": n["lon"], "tags": new_tags, "row": r,
                                  "note": (f"{date.today():%Y-%m-%d}: adopted existing OSM node n{nid} (created {n.get('timestamp', '?')[:10]} by "
                                           f"{n.get('user', 'another mapper')}; carried the atlas Details URL but no ref:US-TX:thc; "
                                           f"{dist:.0f} m from the hmdb coordinate) instead of creating a duplicate.")})

    if (pending or pending_adopt) and not a.stamp_only:
        allrows = pending + pending_adopt
        thcs = [r["ref:US-TX:thc"].strip() for r in allrows if r["ref:US-TX:thc"].strip()]
        hmdbs = [r["ref:hmdb"].strip() for r in allrows]
        print("\n[LIVE] Overpass: any Texas node already holding one of these refs?")
        world = live_ref_holders(thcs, hmdbs)
        world = {nid: t for nid, t in world.items() if nid not in adopt.values()}
        if world:
            for nid, t in world.items():
                print(f"   node/{nid}: thc={t.get('ref:US-TX:thc')} hmdb={t.get('ref:hmdb')} name={t.get('name')!r}")
            raise SystemExit("[ABORT] refs already present on OSM; re-run dedup / decide adoptions")
        print("   none - clear to write")
        updates = [{"node_id": -i, "tags": atlas_tags(r)} for i, r in enumerate(pending, start=1)] + \
                  [{"node_id": u["node_id"], "tags": u["tags"]} for u in adopt_updates]
        try:
            print(f"[OK] validate_ref_plan(thc):  {validate_ref_plan(updates, world)}")
            print(f"[OK] validate_ref_plan(hmdb): {validate_ref_plan(updates, world, tag='ref:hmdb')}")
        except RefPlanError as e:
            raise SystemExit(f"[ABORT] {e}")

    if a.dry_run:
        print("\n=== DRY RUN ===")
        for label, part, brows in batches:
            t = changeset_tags(len(brows), label, part)
            print(f"\n-- {t['comment']}  ({len(t['comment'])}/255)")
            for r in brows:
                tg = atlas_tags(r)
                print(f"   {tg.get('ref:US-TX:thc', '(no thc#)'):>8} {r['name'][:44]:<44} ({r['verified:Latitude']},{r['verified:Longitude']}) "
                      f"hmdb={tg['ref:hmdb']} {tg.get('addr:city', '')}/{tg.get('addr:county', '')}" + ("  [note: not in THC atlas]" if "note" in tg else ""))
        print("\n[DRY] nothing written")
        return

    if not a.stamp_only:
        for bi, (label, part, brows) in enumerate(batches):
            if bi > 0:
                print(f"\n[PAUSE] {a.pause}s")
                time.sleep(a.pause)
            tags = changeset_tags(len(brows), label, part)
            ops = [{"tmp_id": -i, "row": r, "lat": r["verified:Latitude"].strip(), "lon": r["verified:Longitude"].strip(),
                    "tags": atlas_tags(r)} for i, r in enumerate(brows, start=1)]
            print(f"\n[PUSH] {label}{part}: {len(ops)} nodes")
            cs_id = open_changeset(session, tags=tags)
            print(f"[OK] changeset {cs_id}: https://www.openstreetmap.org/changeset/{cs_id}")
            try:
                new_ids = parse_new_ids(upload_diff(session, cs_id, build_create_osmchange(ops, cs_id)))
                if len(new_ids) != len(ops):
                    raise SystemExit(f"diffResult returned {len(new_ids)} ids for {len(ops)} nodes")
                for op in ops:
                    nid = new_ids[op["tmp_id"]]
                    state["assignments"][row_key(op["row"])] = nid
                    print(f"   + node/{nid}  {op['tags'].get('ref:US-TX:thc', '(no thc#)')} {op['row']['name'][:45]}")
                state["changesets"].append({"id": cs_id, "label": f"{label}{part}", "nodes": len(ops)})
                state_p.write_text(json.dumps(state, indent=2))
            finally:
                close_changeset(session, cs_id)
                print(f"[OK] changeset {cs_id} closed")
        if adopt_updates:
            if batches:
                print(f"\n[PAUSE] {a.pause}s")
                time.sleep(a.pause)
            names = ", ".join(u["row"]["name"] for u in adopt_updates)
            comment = (f"Add ref:US-TX:thc, hmdb.org reference, address and operator to {len(adopt_updates)} existing Texas Historical "
                       f"Commission marker node(s): {names}. Source: atlas.thc.texas.gov + hmdb.org")
            if len(comment) > 255:
                comment = comment[:252] + "..."
            cs_id = open_changeset(session, tags={"created_by": "thc-toolkit/0.1", "comment": comment,
                                                  "source": "atlas.thc.texas.gov; hmdb.org", "bot": "no"})
            print(f"\n[PUSH] adoption: changeset {cs_id}: https://www.openstreetmap.org/changeset/{cs_id}")
            try:
                upload_diff(session, cs_id, build_osmchange([{k: u[k] for k in ("node_id", "version", "lat", "lon", "tags")} for u in adopt_updates], cs_id))
                for u in adopt_updates:
                    state["assignments"][row_key(u["row"])] = u["node_id"]
                    state["adopted"][row_key(u["row"])] = u["note"]
                    print(f"   ~ node/{u['node_id']} {u['row']['name']}")
                state["changesets"].append({"id": cs_id, "label": "adoption", "nodes": len(adopt_updates)})
                state_p.write_text(json.dumps(state, indent=2))
            finally:
                close_changeset(session, cs_id)
                print(f"[OK] changeset {cs_id} closed")

    assignments = dict(state["assignments"])
    expected = len(to_create) + len(adopt_rows)
    if len(assignments) != expected:
        raise SystemExit(f"[ABORT] state has {len(assignments)} assignments for {expected} rows; not stamping")
    by_key = {row_key(r): r for r in cands}
    ids = sorted(assignments.values())
    live: dict[int, dict] = {}
    for i in range(0, len(ids), 50):
        live.update(fetch_nodes_bulk(ids[i:i + 50], session))
    ok = 0
    for k, nid in assignments.items():
        t = live.get(nid, {}).get("tags", {})
        r = by_key[k]
        want_thc = r["ref:US-TX:thc"].strip()
        if t.get("ref:hmdb") == r["ref:hmdb"].strip() and (not want_thc or t.get("ref:US-TX:thc") == want_thc):
            ok += 1
        else:
            print(f"[WARN] node/{nid} tags {t.get('ref:US-TX:thc')!r}/{t.get('ref:hmdb')!r} != atlas {k}")
    print(f"\n[OK] verified {ok}/{len(assignments)} nodes live on OSM")
    if ok != len(assignments):
        raise SystemExit("[ABORT] verification incomplete; atlas not stamped")
    write_atlas(a.atlas, assignments, state.get("adopted", {}))
    print("changesets:", ", ".join(f"{c['id']} ({c['label']}, {c['nodes']})" for c in state["changesets"]))


if __name__ == "__main__":
    main()

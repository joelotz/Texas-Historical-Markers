#!/usr/bin/env python
"""Push hmdb reference changes from the atlas onto existing OSM nodes, one changeset.

    python .claude/skills/hmdb-update/scripts/retag_nodes.py \
        [--swap THC:OLD_HMDB:NEW_HMDB ...] [--link THC ...] [--atlas atlas_db.csv] [--apply]

--swap  hmdb re-catalogued the marker: the atlas row already holds NEW (Joe or
        a script swapped it), the node still carries OLD. Rewrites ref:hmdb and
        memorial:website only.
--link  the atlas row was just linked to hmdb and already has an OsmNodeID
        (a node created earlier from THC/weebly data). Adds ref:hmdb and
        memorial:website, and pushes addr:full/addr:city/addr:county,
        start_date and website from the atlas when they differ; adds
        operator/operator:wikidata when missing. Never touches name,
        inscription, material or geometry (see feedback_osm_push_scope).

Every node is fetched live and its pre-state asserted (thc# matches the atlas,
ref:hmdb equals OLD for swaps, absent-or-equal for links). validate_ref_plan()
runs on a live Overpass world for every old and new hmdb id, for both ref
tags, before anything is written. The changeset comment is built from the
marker names and asserted <= 255 chars. A state file records the changeset
so a re-run cannot double-push. Without --apply this is a dry run.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "pythonLib"))
from thc_toolkit import osm_refix_direct as D  # noqa: E402

ENDPOINTS = ("https://overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter")
LINK_COLS = ("addr:full", "addr:city", "addr:county", "start_date", "website")


def fold_addr(s: str) -> str:
    """Compare addresses ignoring punctuation, case and spacing (feedback_no_cosmetic_churn_to_osm)."""
    return " ".join("".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).split())


def overpass(q: str) -> dict:
    last = None
    for _ in range(2):
        for ep in ENDPOINTS:
            try:
                r = requests.post(ep, data={"data": q}, timeout=120, headers={"User-Agent": D.DEFAULT_USER_AGENT})
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"   [overpass] {ep}: {e}")
                time.sleep(3)
    raise SystemExit(f"overpass unavailable: {last}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--swap", action="append", default=[], metavar="THC:OLD:NEW")
    ap.add_argument("--link", action="append", default=[], metavar="THC")
    ap.add_argument("--atlas", type=Path, default=ROOT / "atlas_db.csv")
    ap.add_argument("--state", type=Path, default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.swap and not a.link:
        raise SystemExit("nothing to do: pass --swap and/or --link")
    state_p = a.state or ROOT / "scripts/tmp" / f"retag_nodes_{date.today():%Y%m%d}.state.json"

    with a.atlas.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_thc: dict[str, list[dict]] = {}
    for r in rows:
        by_thc.setdefault(r["ref:US-TX:thc"].strip(), []).append(r)

    plan: list[dict] = []          # {thc, node, old, new, mode, row}
    for spec in a.swap:
        thc, old, new = spec.split(":")
        plan.append({"thc": thc, "old": old, "new": new, "mode": "swap"})
    for thc in a.link:
        plan.append({"thc": thc, "old": None, "new": None, "mode": "link"})
    for p in plan:
        cands = [r for r in by_thc.get(p["thc"], []) if r["isActive"].strip() != "False" and r["OsmNodeID"].strip()]
        if len(cands) != 1:
            raise SystemExit(f"thc#{p['thc']}: expected one active atlas row with an OsmNodeID, found {len(cands)}")
        r = cands[0]
        p["row"] = r
        p["node"] = int(r["OsmNodeID"])
        if p["mode"] == "swap" and r["ref:hmdb"].strip() != p["new"]:
            raise SystemExit(f"thc#{p['thc']}: atlas ref:hmdb is {r['ref:hmdb']!r}, not {p['new']!r}; swap the atlas first")
        if p["mode"] == "link":
            if not r["ref:hmdb"].strip():
                raise SystemExit(f"thc#{p['thc']}: atlas row has no ref:hmdb to push")
            p["new"] = r["ref:hmdb"].strip()
    if state_p.exists():
        done = json.loads(state_p.read_text())
        dup = [p["thc"] for p in plan if p["thc"] in done.get("thcs", [])]
        if dup:
            raise SystemExit(f"state file {state_p.name} says already pushed: {dup}")

    session = D.make_session(D.read_josm_oauth_token())
    live = D.fetch_nodes_bulk([p["node"] for p in plan], session)
    updates = []
    for p in plan:
        n = live[p["node"]]
        t = dict(n["tags"])
        r = p["row"]
        if t.get("ref:US-TX:thc") != p["thc"]:
            raise SystemExit(f"n{p['node']}: live ref:US-TX:thc={t.get('ref:US-TX:thc')!r}, expected {p['thc']!r}")
        if p["mode"] == "swap" and t.get("ref:hmdb") != p["old"]:
            raise SystemExit(f"n{p['node']}: live ref:hmdb={t.get('ref:hmdb')!r}, expected old {p['old']!r} (already swapped?)")
        if p["mode"] == "link" and t.get("ref:hmdb") not in (None, p["new"]):
            raise SystemExit(f"n{p['node']}: live ref:hmdb={t.get('ref:hmdb')!r} differs from atlas {p['new']!r}; use --swap")
        before = dict(t)
        t["ref:hmdb"] = p["new"]
        t["memorial:website"] = f"https://www.hmdb.org/m.asp?m={p['new']}"
        if p["mode"] == "link":
            for col in LINK_COLS:
                val = r[col].strip()
                if col == "addr:county" and val.endswith(" County"):
                    val = val[: -len(" County")]
                if val and t.get(col) != val and not (col.startswith("addr:") and fold_addr(t.get(col, "")) == fold_addr(val)):
                    t[col] = val                       # addr flips that only change punctuation/case are cosmetic churn: skip
            t.setdefault("operator", "Texas Historical Commission")
            t.setdefault("operator:wikidata", "Q2397965")
        changed = {k: (before.get(k), t[k]) for k in t if before.get(k) != t[k]}
        print(f"n{p['node']} v{n['version']} thc#{p['thc']} {before.get('name')!r} [{p['mode']}]:")
        if not changed:
            print("     (no change needed)")
            continue
        for k, (o, v) in changed.items():
            print(f"     {k}: {o!r} -> {v!r}")
        updates.append({"node_id": p["node"], "version": n["version"], "lat": n["lat"], "lon": n["lon"], "tags": t, "plan": p})
    if not updates:
        print("[OK] every node already matches the atlas; nothing to push")
        return

    ids = sorted({x for p in plan for x in (p["old"], p["new"]) if x})
    q = "[out:json][timeout:60];(" + "".join(f'node["ref:hmdb"="{i}"];' for i in ids) + ");out tags;"
    world = {int(e["id"]): e.get("tags", {}) for e in overpass(q)["elements"] if e["type"] == "node"}
    print("[OSM] overpass world:", {i: (t.get("ref:hmdb"), t.get("ref:US-TX:thc")) for i, t in world.items()})
    clean = [{k: u[k] for k in ("node_id", "version", "lat", "lon", "tags")} for u in updates]
    print("[OSM] validate_ref_plan(ref:hmdb):", D.validate_ref_plan(clean, world, tag="ref:hmdb"))
    print("[OSM] validate_ref_plan(ref:US-TX:thc):", D.validate_ref_plan(clean, world))

    swaps = [u["plan"] for u in updates if u["plan"]["mode"] == "swap"]
    links = [u["plan"] for u in updates if u["plan"]["mode"] == "link"]
    bits = []
    if swaps:
        bits.append("hmdb.org re-catalogued " + ", ".join(p["row"]["name"] for p in swaps) + " under new ids (old links dead)")
    if links:
        bits.append("add the hmdb ref and address to " + ", ".join(p["row"]["name"] for p in links))
    comment = f"Update hmdb.org references on {len(updates)} Texas Historical Commission marker node(s): " + "; ".join(bits) + "."
    if len(comment) > 255:
        comment = comment[:252] + "..."
    cs_tags = {"created_by": "thc-toolkit/0.1", "comment": comment, "source": "hmdb.org; atlas.thc.texas.gov", "bot": "no"}
    print(f"[OSM] changeset comment ({len(comment)}/255): {comment}")
    if not a.apply:
        print("[DRY] nothing written; re-run with --apply")
        return
    cs = D.open_changeset(session, tags=cs_tags)
    print(f"[OSM] changeset {cs} https://www.openstreetmap.org/changeset/{cs}")
    try:
        resp = D.upload_diff(session, cs, D.build_osmchange(clean, cs))
        print("[OSM] upload:", resp.strip()[:200].replace("\n", " "))
    finally:
        D.close_changeset(session, cs)
        print(f"[OSM] changeset {cs} closed")
    after = D.fetch_nodes_bulk([u["node_id"] for u in updates], session)
    ok = sum(1 for u in updates if after[u["node_id"]]["tags"].get("ref:hmdb") == u["plan"]["new"])
    print(f"[OSM] verified {ok}/{len(updates)} live")
    prev = json.loads(state_p.read_text()) if state_p.exists() else {"thcs": [], "changesets": []}
    prev["thcs"] += [u["plan"]["thc"] for u in updates]
    prev["changesets"].append(cs)
    state_p.write_text(json.dumps(prev, indent=1))


if __name__ == "__main__":
    main()

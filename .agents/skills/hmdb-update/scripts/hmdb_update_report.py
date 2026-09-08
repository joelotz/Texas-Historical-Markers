#!/usr/bin/env python
"""Everything the human needs to approve an hmdb -> atlas update, in one run.

    python .claude/skills/hmdb-update/scripts/hmdb_update_report.py \
        data_files/HMdb-Entries-Texas-YYYYMMDD.csv [--prev OLDER.csv] \
        [--atlas atlas_db.csv] [--out-dir scripts/tmp/hmdb_review_YYYYMMDD] [--no-live]

Nothing here writes to atlas_db.csv. Reconcile runs against a scratch copy in
--out-dir so its auto-apply set can be reviewed before the real run.

Sections (all also written to <out-dir>/report.md):
  0. working tree: uncommitted atlas rows, split into LibreOffice coordinate
     churn vs real edits (the churn must be restored before writing)
  1. snapshot diff: MarkerIDs added/removed since --prev (default: newest
     older export in data_files/)
  2. dead refs: atlas ref:hmdb absent from the new export, classified as
     re-catalogued (replacement found by Marker No./title), Not Yet Published
     (probed live with the session cookie -- Joe's own pending submissions),
     or deleted
  3. Missing-status flips on already-linked rows
  4. reconcile output annotated: new-since-prev, isActive, duplicate thc#
     groups, OSM node, hmdb<->atlas coordinate distance (>2 km flagged),
     address comparison
  5. hmdb-only: added THC-erected pages whose Marker No. is blank or unknown
     to the atlas, with fuzzy matches against un-linked atlas rows (typo'd
     Marker No.) and the nearest atlas row (new-row candidates)
  6. the markdown plan table (name, ref:thc, hmdb url, kind) to show Joe
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "pythonLib"))
from thc_toolkit import hmdb_sync as hs  # noqa: E402

REVIEW_FILES = ("auto_applied.csv", "review_candidates.csv",
                "review_name_mismatches.csv", "review_hmdb_conflicts.csv")
COORD_COLS = ("verified:Latitude", "verified:Longitude", "estimated:Latitude", "estimated:Longitude")
OUT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def load_hmdb(p: Path) -> dict[str, dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {r["MarkerID"].strip(): r for r in csv.DictReader(f) if r["MarkerID"].strip().isdigit()}


def load_atlas(p: Path) -> list[dict]:
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hav(a: float, b: float, c: float, d: float) -> float:
    r = 6371000
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def is_true(v: str) -> bool:
    return (v or "").strip() == "True"


def prev_snapshot(new: Path) -> Path | None:
    cands = sorted(p for p in new.parent.glob("HMdb-Entries-*.csv") if p.name < new.name)
    return cands[-1] if cands else None


# ---------------------------------------------------------------- 0. working tree
def working_tree(atlas: Path) -> None:
    say("## 0. Working tree")
    if ROOT not in atlas.parents:
        say(f"(atlas {atlas} is outside the repo; skipping the git check)")
        return
    num = subprocess.run(["git", "-C", str(ROOT), "diff", "--numstat", "--", str(atlas.relative_to(ROOT))],
                         capture_output=True, text=True).stdout.strip()
    if not num:
        say("clean: atlas_db.csv matches HEAD")
        return
    if (ROOT / ".~lock.atlas_db.csv#").exists():
        say("**Calc has atlas_db.csv open** (lock file present) -- close it before any write")
    head = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{atlas.relative_to(ROOT)}"],
                          capture_output=True).stdout.decode("utf-8")
    old = {}
    for r in csv.DictReader(io.StringIO(head, newline="")):
        old.setdefault(r["ref:US-TX:thc"], []).append(r)
    cur = {}
    for r in load_atlas(atlas):
        cur.setdefault(r["ref:US-TX:thc"], []).append(r)
    churn = 0
    real: dict[str, list[str]] = {}
    for k, rows in cur.items():
        for i, r in enumerate(rows):
            h = old.get(k, [None] * len(rows))[i] if i < len(old.get(k, [])) else None
            if h is None:
                real.setdefault(k, []).append("(new row)")
                continue
            for col in r:
                if h[col] == r[col]:
                    continue
                if col in COORD_COLS:
                    try:
                        if abs(float(h[col]) - float(r[col])) < 1e-8:
                            churn += 1
                            continue
                    except ValueError:
                        pass
                real.setdefault(k, []).append(col)
    say(f"git numstat: {num.split(chr(9))[0]}+ / {num.split(chr(9))[1]}-;  "
        f"LibreOffice coordinate churn cells: {churn};  rows with real edits: {len(real)}")
    for k, cols in list(real.items())[:40]:
        say(f"  thc#{k or '-'}: {', '.join(cols)}")
    if churn:
        say("-> restore the churn first (scripts/tmp/restore_lo_churn_*.py pattern: keep the real-edit rows, "
            "restore HEAD's coordinate strings where values parse equal)")


# ---------------------------------------------------------------- reconcile on scratch copy
def scratch_reconcile(new: Path, atlas: Path, out_dir: Path) -> None:
    scratch = out_dir / "scratch_atlas"
    scratch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(atlas, scratch / "atlas_db.csv")
    ign = atlas.parent / "hmdb_ignore.csv"
    if ign.exists():
        shutil.copy2(ign, scratch / "hmdb_ignore.csv")
    cmd = [sys.executable, "-m", "thc_toolkit.cli", "hmdb", "reconcile", str(new),
           "--atlas", str(scratch / "atlas_db.csv"), "--out-dir", str(out_dir), "--no-backup"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / "pythonLib"))
    say("## Reconcile (scratch copy, atlas untouched)")
    say("```")
    say((r.stdout + r.stderr).strip())
    say("```")
    if r.returncode:
        raise SystemExit("reconcile failed")


# ---------------------------------------------------------------- live probe
def probe_hmdb(mid: str) -> str:
    """'not yet published' | 'live' | 'gone' | 'no cookie' -- uses the fetch cookie."""
    try:
        import requests
        from thc_toolkit import hmdb_fetch as hf
        s = hf.make_session()
    except SystemExit:
        return "no cookie"
    r = s.get(f"https://www.hmdb.org/m.asp?m={mid}", timeout=60)
    txt = re.sub(r"<script.*?</script>", "", r.text, flags=re.S)
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)))
    if "Not Yet Published" in txt:
        return "not yet published"
    if "ErrorReturn" in r.text or len(r.text) < 1000:
        return "gone"
    return "live"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new", type=Path)
    ap.add_argument("--prev", type=Path, default=None)
    ap.add_argument("--atlas", type=Path, default=ROOT / "atlas_db.csv")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-live", action="store_true", help="skip the hmdb.org probes for dead refs")
    a = ap.parse_args()
    new_p = a.new.resolve()
    prev_p = (a.prev or prev_snapshot(new_p))
    if prev_p is None:
        raise SystemExit("no previous snapshot found; pass --prev")
    prev_p = prev_p.resolve()
    tag = re.search(r"(\d{8})", new_p.name)
    stamp = tag.group(1) if tag else f"{date.today():%Y%m%d}"
    out_dir = a.out_dir or ROOT / "scripts/tmp" / f"hmdb_review_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    atlas_p = a.atlas.resolve()

    say(f"# hmdb update report -- {new_p.name} vs {prev_p.name}")
    say(f"atlas: {atlas_p}   review dir: {out_dir}")
    say()
    working_tree(atlas_p)
    say()
    scratch_reconcile(new_p, atlas_p, out_dir)
    say()

    old = load_hmdb(prev_p)
    new = load_hmdb(new_p)
    atlas = load_atlas(atlas_p)
    ign_p = atlas_p.parent / "hmdb_ignore.csv"
    ign = {r["hmdb_MarkerID"].strip(): r for r in csv.DictReader(ign_p.open(encoding="utf-8", newline=""))} if ign_p.exists() else {}
    maxid = max(int(k) for k in new)
    added = sorted(set(new) - set(old), key=int)
    removed = sorted(set(old) - set(new), key=int)
    by_thc: dict[str, list[dict]] = {}
    for r in atlas:
        by_thc.setdefault(r["ref:US-TX:thc"].strip(), []).append(r)
    by_hmdb = {r["ref:hmdb"].strip(): r for r in atlas if r["ref:hmdb"].strip()}

    # ------------------------------------------------------------ 1. snapshot diff
    say("## 1. Snapshot diff")
    say(f"{prev_p.name}: {len(old)} rows;  {new_p.name}: {len(new)} rows (max MarkerID {maxid})")
    thc_added = [m for m in added if hs.is_thc_erected_by(new[m]["Erected By"])]
    say(f"added: {len(added)} ({len(thc_added)} THC-erected)   removed: {len(removed)}")
    for m in removed:
        o = old[m]
        who = f"atlas thc#{by_hmdb[m]['ref:US-TX:thc']}" if m in by_hmdb else ("ignore-list" if m in ign else "unlinked")
        say(f"  removed {m} {o['Title'][:45]!r} MarkerNo={o['Marker No.']!r} -> {who}")
    say()

    # ------------------------------------------------------------ 2. dead refs
    say("## 2. Atlas ref:hmdb values absent from the new export")
    dead = sorted(set(by_hmdb) - set(new), key=int)
    recat: list[tuple[str, str, str, str]] = []   # (thc, old, new, title)
    for m in dead:
        r = by_hmdb[m]
        o = old.get(m)
        cands = []
        if o:
            cands = [n for n in new.values() if o["Marker No."].strip() and n["Marker No."].strip() == o["Marker No."].strip()]
            cands += [n for n in new.values() if hs.normalize_name(n["Title"]) == hs.normalize_name(o["Title"]) and n not in cands]
        cands += [n for n in new.values() if r["ref:US-TX:thc"].strip() and n["Marker No."].strip() == r["ref:US-TX:thc"].strip() and n not in cands]
        cands = [n for n in cands if n["MarkerID"] not in by_hmdb]
        status = "post-pull id (above export max)" if int(m) > maxid else ("" if a.no_live else probe_hmdb(m))
        line = f"  {m} thc#{r['ref:US-TX:thc']} {r['name'][:40]!r} | in prev export: {m in old} | osm={r['OsmNodeID'] or '-'} | {status or 'not probed'}"
        if cands:
            c = cands[0]
            recat.append((r["ref:US-TX:thc"].strip(), m, c["MarkerID"], c["Title"]))
            line += f" | RE-CATALOGUED -> {c['MarkerID']} MarkerNo={c['Marker No.']} {c['Title'][:35]!r} {c['County or Parish']}"
        say(line)
    if not dead:
        say("  none")
    say()

    # ------------------------------------------------------------ 3. missing flips
    say("## 3. Missing-status flips on linked rows")
    n_flip = 0
    for m, r in by_hmdb.items():
        if m not in new:
            continue
        hm = new[m]["Missing"].strip().lower() in hs.MISSING_FLAGS
        if hm != is_true(r["isMissing"]):
            n_flip += 1
            say(f"  {m} thc#{r['ref:US-TX:thc']} {r['name'][:40]!r}: hmdb Missing={new[m]['Missing']!r} "
                f"(prev export: {old.get(m, {}).get('Missing', 'n/a')!r}) vs atlas isMissing={r['isMissing']} | osm={r['OsmNodeID'] or '-'}")
    if not n_flip:
        say("  none")
    say("  (rule: Reported Missing -> isMissing=True, keep the OSM node; Confirmed Missing -> isMissing=True and ask Joe about the node; "
        "atlas True vs hmdb blank -> ask, hmdb usually wins)")
    say()

    # ------------------------------------------------------------ 4. reconcile annotated
    say("## 4. Reconcile output, annotated")
    say("dist = hmdb coordinate vs atlas coordinate (v = verified, e = estimated); >2 km flagged <<<")
    plan: list[tuple[str, str, str, str]] = []
    for fn in REVIEW_FILES:
        rows = list(csv.DictReader((out_dir / fn).open(encoding="utf-8", newline="")))
        say(f"### {fn} ({len(rows)})")
        for x in rows:
            mid, thc = x["hmdb_MarkerID"], x["ref:US-TX:thc"]
            n = new.get(mid, {})
            ar = by_thc.get(thc, [])
            act = next((r for r in ar if r["isActive"].strip() != "False"), ar[0] if ar else None)
            flags = ["NEW" if mid in added else "existed in prev export"]
            if mid in old and old[mid]["Marker No."].strip() != n.get("Marker No.", "").strip():
                flags.append(f"MarkerNo changed {old[mid]['Marker No.']!r}->{n['Marker No.']!r}")
            if len(ar) > 1:
                flags.append(f"dup-thc-group({len(ar)})")
            for r in ar:
                if r["isActive"].strip() == "False":
                    flags.append("isActive=False row (superseded; usually NO)")
                if r["ref:hmdb"].strip():
                    flags.append(f"atlas ref:hmdb={r['ref:hmdb']}")
                if r["OsmNodeID"].strip():
                    flags.append(f"osm={r['OsmNodeID']}")
                if is_true(r["isMissing"]):
                    flags.append("atlas isMissing")
            dist = "n/a"
            src = "-"
            if act:
                try:
                    src = "v" if act["verified:Latitude"].strip() else "e"
                    al = float(act["verified:Latitude"] or act["estimated:Latitude"])
                    an = float(act["verified:Longitude"] or act["estimated:Longitude"])
                    d = hav(float(n["Latitude (minus=S)"]), float(n["Longitude (minus=W)"]), al, an)
                    dist = f"{d / 1000:.2f} km" + (" <<<" if d > 2000 else "")
                except (ValueError, KeyError):
                    pass
            say(f"  {mid} thc#{thc:>6} {dist:>10}({src}) | hmdb={n.get('Title', '')[:38]!r} atlas={(act['name'] if act else '?')[:38]!r} "
                f"| {n.get('County or Parish', '')} / {(act['addr:county'] if act else '?')} | Missing={n.get('Missing', '')!r} "
                f"| score={x.get('name_similarity', '')} | hmdb addr {n.get('Street Address', '')[:28]!r}, {n.get('City or Town', '')} "
                f"vs atlas {(act['addr:full'][:28] if act else '')!r}, {(act['addr:city'] if act else '')} | {'; '.join(flags)}"
                + (f" | existing={x['atlas_existing_ref:hmdb']}" if "atlas_existing_ref:hmdb" in x else ""))
            kind = {"auto_applied.csv": "new link, exact name",
                    "review_candidates.csv": f"new link, near-exact name (hmdb: “{x['hmdb_Title']}”)",
                    "review_name_mismatches.csv": f"new link, name differs (hmdb: “{x['hmdb_Title']}”) -- check",
                    "review_hmdb_conflicts.csv": f"conflict: atlas holds {x.get('atlas_existing_ref:hmdb')}"}[fn]
            if fn == "review_hmdb_conflicts.csv" and any(rc[2] == mid for rc in recat):
                kind = f"re-catalogued id, was {x.get('atlas_existing_ref:hmdb')}; OSM node tags too" if act and act["OsmNodeID"].strip() \
                    else f"re-catalogued id, was {x.get('atlas_existing_ref:hmdb')}"
            if act and act["isActive"].strip() == "False" and fn != "auto_applied.csv":
                kind = "SKIP: superseded atlas row"
            plan.append((act["name"] if act else x["hmdb_Title"], thc, f"https://www.hmdb.org/m.asp?m={mid}", kind))
        say()

    # ------------------------------------------------------------ 5. hmdb-only
    say("## 5. Added THC-erected pages the atlas cannot place by Marker No.")
    unlinked = [r for r in atlas if not r["ref:hmdb"].strip() and r["isActive"].strip() != "False"]
    n_only = 0
    for m in thc_added:
        n = new[m]
        mno = n["Marker No."].strip()
        if (mno and mno in by_thc) or m in ign or n["Missing"].strip().lower() in hs.MISSING_FLAGS:
            continue
        n_only += 1
        try:
            la, lo = float(n["Latitude (minus=S)"]), float(n["Longitude (minus=W)"])
        except ValueError:
            la = lo = None
        county = re.sub(r"\s+County$", "", n["County or Parish"].strip())
        scored = []
        for r in unlinked:
            sim = hs.name_similarity(n["Title"], r["name"])
            if sim < 0.7:
                continue
            same = re.sub(r"\s+County$", "", r["addr:county"].strip()) == county
            try:
                d = hav(la, lo, float(r["verified:Latitude"] or r["estimated:Latitude"]),
                        float(r["verified:Longitude"] or r["estimated:Longitude"])) if la is not None else None
            except ValueError:
                d = None
            scored.append((same, round(sim, 2), -(d if d is not None else 1e9), r["ref:US-TX:thc"], r["name"][:32], r["addr:county"], d))
        scored.sort(reverse=True)
        best = [(sim, thc_, nm, cty, f"{d:.0f} m" if d is not None else "no coord") for same, sim, _, thc_, nm, cty, d in scored[:3]]
        nearest = None
        if la is not None:
            best_d = None
            for r in atlas:
                for cols in (("verified:Latitude", "verified:Longitude"), ("estimated:Latitude", "estimated:Longitude")):
                    try:
                        d = hav(la, lo, float(r[cols[0]]), float(r[cols[1]]))
                    except ValueError:
                        continue
                    if best_d is None or d < best_d:
                        best_d, nearest = d, r
                    break
            nearest = f"nearest atlas row {best_d:.0f} m: thc#{nearest['ref:US-TX:thc']} {nearest['name'][:30]!r} (ref:hmdb {nearest['ref:hmdb'] or '-'})" if nearest else "none"
        say(f"  {m} MarkerNo={mno!r} {n['Title'][:42]!r} | {n['County or Parish']} / {n['City or Town']} | {n['Year Erected']} "
            f"| erected by {n['Erected By'][:40]!r} | https://www.hmdb.org/m.asp?m={m}")
        say(f"        un-linked atlas name matches: {best or 'none'} | {nearest}")
        if best and best[0][0] >= 0.95 and best[0][3].startswith(county):
            plan.append((best[0][2], best[0][1], f"https://www.hmdb.org/m.asp?m={m}",
                         f"hmdb Marker No. {mno or '(blank)'} looks wrong; likely thc#{best[0][1]} ({best[0][4]} away) -- verify date/inscription, cross-map by MarkerID"))
        else:
            plan.append((n["Title"], "(none)", f"https://www.hmdb.org/m.asp?m={m}",
                         "not in the atlas -- new row candidate (ask Joe)" if not mno else f"hmdb Marker No. {mno} unknown to the atlas -- check THC export"))
    if not n_only:
        say("  none")
    say()

    # ------------------------------------------------------------ 6. plan table
    say("## 6. Plan table")
    say("| Name (atlas) | ref:thc | hmdb url | kind |")
    say("|---|---|---|---|")
    for name, thc, url, kind in plan:
        say(f"| {name} | {thc} | {url} | {kind} |")
    say()
    say(f"counts: {Counter(k.split(',')[0].split(':')[0] for _, _, _, k in plan)}")
    (out_dir / "report.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"\n[report written to {out_dir / 'report.md'}]")


if __name__ == "__main__":
    main()

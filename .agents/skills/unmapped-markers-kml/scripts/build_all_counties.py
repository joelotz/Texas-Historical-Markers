#!/usr/bin/env python3
"""Build unmapped-marker KMLs for every county — incrementally.

Wraps the single-county build_kml.py and only rebuilds counties whose
KML-eligible rows have changed since the last run. A per-county content
hash is persisted in a state file; unchanged counties are skipped, new/
changed counties are rebuilt, and counties that no longer have any
eligible rows have their stale KML + sidecar pruned.

Nominatim geocoding is DISABLED by default (the workflow pre-geocodes via
the US Census batch, then builds). Pass --geocode to re-enable it.

Usage:
  # incremental: only rebuild what changed
  python3 build_all_counties.py

  # force a full rebuild of every county
  python3 build_all_counties.py --all

  # limit to specific counties (still honors change detection unless --all)
  python3 build_all_counties.py --county Tarrant --county Dallas

State file defaults to <repo>/scripts/tmp/kml_build_state.json (gitignored).
"""
import argparse
import csv
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_kml  # noqa: E402


def eligible_rows_by_county(atlas: Path) -> dict[str, list[dict]]:
    """Group the KML-eligible rows (same filter as build_kml) by county."""
    out: dict[str, list[dict]] = {}
    with atlas.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = r["addr:county"].strip()
            if not c:
                continue
            if r["ref:hmdb"].strip():
                continue
            if r["isMissing"].strip() == "True" or r["isPrivate"].strip() == "True":
                continue
            out.setdefault(c, []).append(r)
    return out


def county_hash(rows: list[dict]) -> str:
    """Stable hash over a county's eligible rows (all columns)."""
    rows_sorted = sorted(rows, key=lambda r: r["ref:US-TX:thc"])
    blob = json.dumps(rows_sorted, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "atlas": None, "counties": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def build_one(county: str, atlas: Path, out_dir: Path) -> str:
    """Invoke build_kml.main() for one county; return its 'KML:' summary."""
    argv_bak = sys.argv
    sys.argv = ["build_kml", "--county", county,
                "--atlas", str(atlas), "--out-dir", str(out_dir)]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            build_kml.main()
    except SystemExit:
        pass
    finally:
        sys.argv = argv_bak
    for line in buf.getvalue().splitlines():
        if line.startswith("KML:"):
            return line[5:].strip()
    return "(built)"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--atlas", default="atlas_db.csv")
    p.add_argument("--out-dir", default="unmapped markers")
    p.add_argument("--state", default=None,
                   help="State file (default <repo>/scripts/tmp/kml_build_state.json)")
    p.add_argument("--all", "--force", action="store_true", dest="force",
                   help="Rebuild every county, ignoring change detection")
    p.add_argument("--county", action="append", default=[],
                   help="Limit to these counties (repeatable)")
    p.add_argument("--geocode", action="store_true",
                   help="Enable Nominatim geocoding (default off)")
    p.add_argument("--no-prune", action="store_true",
                   help="Do not delete KMLs for counties with no eligible rows")
    args = p.parse_args()

    atlas = Path(args.atlas).resolve()
    out_dir = Path(args.out_dir)
    repo = atlas.parent
    state_path = Path(args.state).resolve() if args.state else \
        repo / "scripts" / "tmp" / "kml_build_state.json"

    if not args.geocode:
        # Neutralize Nominatim: coord-less rows fall through to the sidecar.
        build_kml.geocode = lambda *a, **k: None

    by_county = eligible_rows_by_county(atlas)
    cur_hashes = {c: county_hash(rows) for c, rows in by_county.items()}

    state = load_state(state_path)
    prev = state.get("counties", {})
    if state.get("atlas") not in (None, str(atlas)):
        print(f"[note] state was for a different atlas ({state.get('atlas')}); "
              f"treating all counties as changed")
        prev = {}

    only = set(args.county) if args.county else None

    rebuilt, skipped = [], []
    for county in sorted(cur_hashes):
        if only and county not in only:
            skipped.append(county)
            continue
        changed = args.force or prev.get(county) != cur_hashes[county]
        if not changed:
            skipped.append(county)
            continue
        summary = build_one(county, atlas, out_dir)
        rebuilt.append(county)
        print(f"[build] {county}: {summary}")

    # Prune counties that no longer have eligible rows (stale files on disk).
    pruned = []
    if not args.no_prune and not only:
        eligible = set(cur_hashes)
        for kml in sorted(out_dir.glob("*_unmapped_markers.kml")):
            county = kml.name[: -len("_unmapped_markers.kml")]
            if county not in eligible:
                kml.unlink(missing_ok=True)
                (out_dir / f"{county}_unmapped_no_coords.txt").unlink(missing_ok=True)
                pruned.append(county)
                print(f"[prune] {county}: removed stale KML + sidecar")

    # Persist new state (only when we did a complete pass, i.e. no --county subset).
    if not only:
        state = {"version": 1, "atlas": str(atlas), "counties": cur_hashes}
        save_state(state_path, state)

    print(f"\n[done] rebuilt {len(rebuilt)}, skipped {len(skipped)}, "
          f"pruned {len(pruned)}  (state: {state_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

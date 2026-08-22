#!/usr/bin/env python3
"""
Build ONE Google My Maps-ready KML covering every unmapped historical marker
in Texas.

"Unmapped" uses the same filter as build_kml.py: atlas_db.csv row where
`ref:hmdb` is empty AND `isMissing` is not True AND `isPrivate` is not True
AND `isActive` is not False.

Differences from build_kml.py (which is county-scoped):
  * No geocoding. A statewide pass would be thousands of Nominatim requests;
    coord-less rows go to the sidecar instead. Pre-geocode per county with
    build_kml.py / audit_coords.py if you want them on the map.
  * `verified:Latitude/Longitude` is preferred over `estimated:*` when both
    exist, and is used alone when it is the only coord on the row.
  * Placemarks are split across <Folder> elements, each holding whole
    counties and at most --max-per-folder marks. Google My Maps imports one
    KML <Folder> per layer and silently truncates a layer past 2,000 rows.
  * The popup carries the county, since a statewide map spans 200+ of them.

Usage:
  python3 build_statewide_kml.py
  python3 build_statewide_kml.py --out "unmapped markers/Texas_statewide_unmapped.kml"
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_kml  # noqa: E402  (shared filter/description/style logic)

# Google My Maps caps a layer at 2,000 features and a map at 10 layers.
MAX_PER_FOLDER = 2000


def coords(r: dict):
    """Best coordinate on the row, and its provenance.

    verified:* is a field-measured coord and beats the THC-derived
    estimated:* whenever it is present.
    """
    vlat, vlon = r["verified:Latitude"].strip(), r["verified:Longitude"].strip()
    if vlat and vlon:
        return vlat, vlon, "verified"
    elat, elon = r["estimated:Latitude"].strip(), r["estimated:Longitude"].strip()
    if elat and elon:
        return elat, elon, "estimated"
    return None


def eligible(atlas: Path):
    with atlas.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f)
                if not r["ref:hmdb"].strip()
                and r["isMissing"].strip().lower() != "true"
                and r["isPrivate"].strip().lower() != "true"
                and r["isActive"].strip().lower() != "false"]


def placemark(r: dict, lat: str, lon: str) -> str:
    pending = build_kml.is_pending(r)
    name = ("[PENDING] " if pending else "") + r["name"]
    body = build_kml.desc(r, county=r["addr:county"].strip())
    return (
        "  <Placemark>\n"
        f"    <name>{escape(name)}</name>\n"
        f'    <styleUrl>#{"pending" if pending else "normal"}</styleUrl>\n'
        f"    <description><![CDATA[{body}]]></description>\n"
        f"    <Point><coordinates>{lon},{lat},0</coordinates></Point>\n"
        "  </Placemark>"
    )


def folders(by_county: dict, cap: int):
    """Greedily pack counties (alphabetical) into folders of at most `cap` marks.

    Counties are never split across folders, so a layer always holds whole
    counties and the folder name can be stated as a county range.
    """
    out, cur, n = [], [], 0
    for county in sorted(by_county):
        rows = by_county[county]
        if cur and n + len(rows) > cap:
            out.append(cur)
            cur, n = [], 0
        cur.append(county)
        n += len(rows)
    if cur:
        out.append(cur)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--atlas", default="atlas_db.csv")
    p.add_argument("--out", default="unmapped markers/Texas_statewide_unmapped.kml")
    p.add_argument("--sidecar", default="unmapped markers/Texas_statewide_no_coords.txt")
    p.add_argument("--max-per-folder", type=int, default=MAX_PER_FOLDER,
                   help="Max placemarks per <Folder>; My Maps truncates a layer past 2000")
    args = p.parse_args()

    atlas = Path(args.atlas).resolve()
    out_path = Path(args.out).resolve()
    side_path = Path(args.sidecar).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = eligible(atlas)
    by_county = defaultdict(list)
    no_coords = []
    n_verified = n_pending = 0
    for r in rows:
        c = coords(r)
        if not c:
            no_coords.append(r)
            continue
        lat, lon, src = c
        n_verified += src == "verified"
        n_pending += build_kml.is_pending(r)
        by_county[r["addr:county"].strip() or "(no county)"].append((r, lat, lon))

    total = sum(len(v) for v in by_county.values())
    groups = folders(by_county, args.max_per_folder)

    chunks = []
    for g in groups:
        marks = []
        for county in g:
            for r, lat, lon in sorted(by_county[county], key=lambda x: x[0]["name"].lower()):
                marks.append(placemark(r, lat, lon))
        label = g[0] if len(g) == 1 else f"{g[0]}–{g[-1]}"
        chunks.append(
            "  <Folder>\n"
            f"    <name>{escape(label)} ({len(marks)} markers)</name>\n"
            f"    <description>{len(g)} counties: {escape(', '.join(g))}</description>\n"
            + "\n".join(marks)
            + "\n  </Folder>"
        )

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "<Document>\n"
        "  <name>Texas — Unmapped Historical Markers (statewide)</name>\n"
        f"  <description>Every THC marker in Texas without an HMDB id, excluding "
        f"isMissing, isPrivate and isActive=False rows. {total} placemarks across "
        f"{len(by_county)} counties ({n_verified} on field-verified coords, the rest "
        f"on THC estimated coords); {len(no_coords)} further markers are omitted for "
        f"having no coordinate at all. Orange pins ({n_pending}) are isPending=True — "
        f"the marker may not be installed yet. Split into {len(groups)} folders because "
        f"Google My Maps caps a layer at 2,000 features.</description>\n"
        + build_kml.STYLES
        + "\n".join(chunks)
        + "\n</Document>\n</kml>\n"
    )
    out_path.write_text(kml, encoding="utf-8")

    with side_path.open("w", encoding="utf-8") as f:
        f.write(f"Texas unmapped markers with NO coordinate ({len(no_coords)}):\n\n")
        for r in sorted(no_coords, key=lambda x: (x["addr:county"], x["name"].lower())):
            addr = ", ".join(b for b in [r["addr:full"].strip(), r["addr:city"].strip()] if b)
            f.write(f'  THC {r["ref:US-TX:thc"]} [{r["addr:county"]}]: {r["name"]}\n')
            if addr:
                f.write(f"    addr: {addr}\n")
            f.write(f'    {r["website"]}\n\n')

    print(f"KML: {out_path}")
    print(f"  {total} placemarks / {len(by_county)} counties / {len(groups)} folders "
          f"/ {out_path.stat().st_size / 1_048_576:.2f} MB")
    for g, chunk in zip(groups, chunks):
        print(f"    {g[0]}–{g[-1]}: {chunk.count('<Placemark>')} markers, {len(g)} counties")
    print(f"Sidecar: {side_path}  ({len(no_coords)} markers with no coordinate)")


if __name__ == "__main__":
    raise SystemExit(main())

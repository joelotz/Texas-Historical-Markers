#!/usr/bin/env python3
"""
Build ONE KML of every *mapped* Texas historical marker — the rows carrying a
field-verified coordinate (`verified:Latitude` + `verified:Longitude`).

This is the mirror image of build_statewide_kml.py. That one maps markers still
to be found; this one maps the ~12.8k already pinned down, as a coverage /
reference layer.

`isMissing=True` rows are excluded, matching the other builders in this skill —
a marker that is gone is not coverage. `isPrivate` and `isOSM=False` rows are
kept, distinguished by pin colour and a name prefix:

  green   on OSM, nothing special           (the normal case)
  blue    [NO OSM NODE] not yet in OSM
  purple  [PRIVATE] on private property

Precedence when a row qualifies for both: private > no-OSM.

Popups carry Marker Notes, address, county, the HMDB and OSM links, and the
full Marker Text. The THC Atlas link and `thc:designation` stay out — Joe
called them noise on the unmapped map and the same holds here. `DATA_NOTE`
never appears.

Output defaults into `generated/`, which is gitignored: at ~12 MB this is a
derived artifact that rebuilds from atlas_db.csv in a couple of seconds and has
no business in git history.

Usage:
  python3 build_mapped_kml.py
  python3 build_mapped_kml.py --no-marker-text            # drop Marker Text
  python3 build_mapped_kml.py --no-marker-text --kmz      # slim, zipped
"""
import argparse
import csv
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

# Google's hosted pin set. Sticking to these eight names keeps the icons
# resolvable; a colour override alone is not enough in every renderer.
STYLES = "".join(
    f'  <Style id="{sid}">\n'
    f"    <IconStyle>\n"
    f"      <Icon><href>http://maps.google.com/mapfiles/ms/icons/{icon}.png</href></Icon>\n"
    f"    </IconStyle>\n"
    f"  </Style>\n"
    for sid, icon in (
        ("osm", "green-dot"),
        ("noosm", "blue-dot"),
        ("private", "purple-dot"),
    )
)


def is_true(r: dict, k: str) -> bool:
    return r[k].strip().lower() == "true"


def classify(r: dict):
    """(style id, name prefix) for one row."""
    if is_true(r, "isPrivate"):
        return "private", "[PRIVATE] "
    if not is_true(r, "isOSM"):
        return "noosm", "[NO OSM NODE] "
    return "osm", ""


def desc(r: dict, marker_text: bool) -> str:
    """Popup body.

    `Marker Notes` is written for a person standing at the roadside; it belongs
    here. `DATA_NOTE` is coordinate provenance and sync bookkeeping for whoever
    maintains the atlas, and must never reach the popup.
    """
    parts = []
    if is_true(r, "isPrivate"):
        parts.append("<b>⚠ On private property — do not trespass.</b>")
    if r["Marker Notes"].strip():
        parts.append(escape(r["Marker Notes"].strip()))

    addr = ", ".join(b for b in [r["addr:full"].strip(), r["addr:city"].strip()] if b)
    if addr:
        parts.append(f"<b>Address:</b> {escape(addr)}")
    if r["addr:county"].strip():
        parts.append(f'<b>County:</b> {escape(r["addr:county"].strip())}')

    links = []
    if r["memorial:website"].strip():
        links.append(f'<a href="{escape(r["memorial:website"].strip())}">HMDB</a>')
    if r["OsmNodeID"].strip():
        node = r["OsmNodeID"].strip()
        links.append(f'<a href="https://www.openstreetmap.org/node/{escape(node)}">OSM node {escape(node)}</a>')
    if links:
        parts.append(" &middot; ".join(links))

    if marker_text and r["Marker Text"].strip():
        parts.append(f'<b>Marker Text:</b> {escape(r["Marker Text"].strip())}')
    return "<br/><br/>".join(parts)


def placemark(r: dict, marker_text: bool) -> str:
    style, prefix = classify(r)
    return (
        "    <Placemark>\n"
        f'      <name>{escape(prefix + r["name"])}</name>\n'
        f"      <styleUrl>#{style}</styleUrl>\n"
        f"      <description><![CDATA[{desc(r, marker_text)}]]></description>\n"
        f'      <Point><coordinates>{r["verified:Longitude"].strip()},'
        f'{r["verified:Latitude"].strip()},0</coordinates></Point>\n'
        "    </Placemark>"
    )


def split_east_west(by_county: dict, parts: int):
    """Cut the counties into `parts` groups of roughly equal marker count.

    Counties are ordered by mean longitude and packed west to east, so each
    part is a contiguous north-south slab of Texas rather than a scattering.
    Counties are never split across parts.
    """
    def lon(c):
        vals = [float(r["verified:Longitude"]) for r in by_county[c]]
        return sum(vals) / len(vals)

    ordered = sorted(by_county, key=lon)
    total = sum(len(by_county[c]) for c in ordered)
    groups, cur, n = [], [], 0
    for i, county in enumerate(ordered):
        cur.append(county)
        n += len(by_county[county])
        remaining_parts = parts - len(groups)
        # Close this part once it holds its share, unless the counties left
        # are only just enough to fill the parts still owed.
        if remaining_parts > 1 and n >= total / parts and len(ordered) - i - 1 >= remaining_parts - 1:
            groups.append(cur)
            cur, n = [], 0
    if cur:
        groups.append(cur)
    return groups


def build_doc(counties, by_county, marker_text: bool, max_per_folder: int, title: str, note: str):
    """One KML document over `counties`, folder-split to respect the layer cap."""
    tally = defaultdict(int)
    by_name = {}
    for county in sorted(counties):
        marks = []
        for r in sorted(by_county[county], key=lambda x: x["name"].lower()):
            tally[classify(r)[0]] += 1
            marks.append(placemark(r, marker_text))
        by_name[county] = marks

    # Google My Maps makes one layer per <Folder> and silently truncates a
    # layer past 2000 rows, so counties are packed into folders under that cap
    # rather than getting a folder each.
    chunks, cur, n = [], [], 0
    for county in sorted(by_name):
        marks = by_name[county]
        if cur and n + len(marks) > max_per_folder:
            chunks.append(cur)
            cur, n = [], 0
        cur.append(county)
        n += len(marks)
    if cur:
        chunks.append(cur)

    folders = []
    for g in chunks:
        marks = [m for c in g for m in by_name[c]]
        label = g[0] if len(g) == 1 else f"{g[0]}\u2013{g[-1]}"
        folders.append(
            "  <Folder>\n"
            f"    <name>{escape(label)} ({len(marks)})</name>\n"
            f"    <description>{len(g)} counties: {escape(', '.join(g))}</description>\n"
            + "\n".join(marks)
            + "\n  </Folder>"
        )

    total = sum(len(v) for v in by_name.values())
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "<Document>\n"
        f"  <name>{escape(title)}</name>\n"
        f"  <description>{total} THC markers carrying a field-verified coordinate, "
        f"across {len(by_name)} counties in {len(folders)} folders. {escape(note)}"
        f"Markers reported missing are excluded. Green = on OSM ({tally['osm']}); "
        f"blue = not yet in OSM ({tally['noosm']}); purple = private property "
        f"({tally['private']}). Built from atlas_db.csv.</description>\n"
        + STYLES
        + "\n".join(folders)
        + "\n</Document>\n</kml>\n"
    )
    return kml, total, tally, len(folders)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--atlas", default="atlas_db.csv")
    p.add_argument("--out", default="generated/Texas_mapped_markers.kml")
    p.add_argument("--no-marker-text", action="store_true",
                   help="Omit Marker Text from popups (~16 MB -> ~6 MB)")
    p.add_argument("--kmz", action="store_true",
                   help="Write a zipped .kmz (doc.kml inside) instead of a plain .kml")
    p.add_argument("--split", type=int, default=1, metavar="N",
                   help="Write N files, cut west-to-east into equal marker counts. "
                        "My Maps measures its 5 MB limit on the UNZIPPED kml, so a "
                        "kmz does not get you under it -- splitting does.")
    p.add_argument("--max-per-folder", type=int, default=2000,
                   help="Max placemarks per <Folder>; My Maps truncates a layer past 2000")
    args = p.parse_args()

    atlas = Path(args.atlas).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    marker_text = not args.no_marker_text

    with atlas.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["verified:Latitude"].strip() and r["verified:Longitude"].strip()
                and not is_true(r, "isMissing")]

    by_county = defaultdict(list)
    for r in rows:
        by_county[r["addr:county"].strip() or "(no county)"].append(r)

    if args.split > 1:
        groups = split_east_west(by_county, args.split)
    else:
        groups = [list(by_county)]

    for i, counties in enumerate(groups, 1):
        if len(groups) > 1:
            title = f"Texas Mapped Markers {i}/{len(groups)} (field-verified coords)"
            note = f"Part {i} of {len(groups)}, cut west to east. "
            stem = f"{out_path.stem}_part{i}of{len(groups)}"
        else:
            title = "Texas \u2014 Mapped Historical Markers (field-verified coords)"
            note = ""
            stem = out_path.stem

        kml, total, tally, n_folders = build_doc(
            counties, by_county, marker_text, args.max_per_folder, title, note)
        raw_mb = len(kml.encode("utf-8")) / 1_048_576

        if args.kmz:
            # A .kmz is a zip whose entry point is doc.kml. Good for transport,
            # useless for My Maps -- it unzips first, then applies the 5 MB cap
            # to the kml inside.
            dest = out_path.with_name(stem + ".kmz")
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                z.writestr("doc.kml", kml)
        else:
            dest = out_path.with_name(stem + ".kml")
            dest.write_text(kml, encoding="utf-8")

        flag = "" if raw_mb < 5 else "   <-- OVER the My Maps 5 MB cap"
        print(f"{'KMZ' if args.kmz else 'KML'}: {dest}")
        print(f"  {total} placemarks / {len(counties)} counties / {n_folders} folders")
        print(f"  {raw_mb:.2f} MB unzipped{flag}"
              + (f" ({dest.stat().st_size / 1_048_576:.2f} MB on disk)" if args.kmz else "")
              + ("  (no Marker Text)" if not marker_text else ""))
        for k, label in (("osm", "on OSM"), ("noosm", "not in OSM"),
                         ("private", "private property")):
            print(f"    {label:20s} {tally[k]:>6}")


if __name__ == "__main__":
    raise SystemExit(main())

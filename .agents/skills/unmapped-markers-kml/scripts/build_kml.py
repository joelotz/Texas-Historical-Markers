#!/usr/bin/env python3
"""
Build a Google My Maps-ready KML of unmapped historical markers for a county.

"Unmapped" = atlas_db.csv row where `ref:hmdb` is empty AND `isMissing` is not True
AND `isPrivate` is not True AND `isActive` is not False.

Behavior:
  1. Filter atlas_db.csv to the requested county.
  2. Markers with `estimated:Latitude`/`estimated:Longitude` go straight into the KML.
  3. Markers without coords but with a street-level address (digit in addr:full)
     are geocoded via OSM Nominatim (1 req/sec, polite User-Agent).
  4. Geocoded coords are written back to atlas_db.csv by default so future
     runs skip the lookup. Use --no-write-coords to disable.
  5. Markers with `isPending=True` are flagged in the KML title with
     `[PENDING]` and a warning note in the description.
  6. Markers with no coords AND no usable street address are written to a
     sidecar text file so the user can locate them manually later.

Usage:
  python3 build_kml.py --county Tarrant
  python3 build_kml.py --county Denton --atlas /path/to/atlas_db.csv --out-dir /path/to/output
  python3 build_kml.py --county Tarrant --no-write-coords
"""
import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

NOMINATIM = 'https://nominatim.openstreetmap.org/search'
UA = 'TX-HistoricalMarkers-UnmappedKML/1.0'


def has_street_address(addr: str) -> bool:
    return any(c.isdigit() for c in addr)


def geocode(addr: str, city: str, timeout: int = 15):
    q = ', '.join(b for b in [addr, city, 'Texas', 'USA'] if b)
    url = f'{NOMINATIM}?{urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    if data:
        return float(data[0]['lat']), float(data[0]['lon']), data[0].get('display_name', '')
    return None


def is_pending(r: dict) -> bool:
    return r['isPending'].strip().lower() == 'true'


def desc(r: dict, geocoded_note: str | None = None, county: str | None = None) -> str:
    """Popup body for one marker.

    `Marker Notes` is written for the person trying to find the marker —
    directions, landmarks, what to look for. It belongs here.

    `DATA_NOTE` is for whoever maintains the data — coordinate provenance,
    duplicate adjudications, sync history. It must never appear in the popup;
    it is noise to a reader standing at a roadside.
    """
    parts = []
    if is_pending(r):
        parts.append('<b>⚠ PENDING — marker may not yet be installed at this location.</b>')
    if r['Marker Notes'].strip():
        parts.append(escape(r['Marker Notes'].strip()))
    addr_bits = [r['addr:full'].strip(), r['addr:city'].strip()]
    addr = ', '.join(b for b in addr_bits if b)
    if addr:
        parts.append(f'<b>Address:</b> {escape(addr)}')
    # Statewide builds pass `county`; a county-scoped KML already says it in the
    # document title, so it stays out of the popup there.
    if county:
        parts.append(f'<b>County:</b> {escape(county)}')
    if geocoded_note:
        parts.append(
            f'<i>Coordinates derived by geocoding the address — may be approximate. '
            f'Match: {escape(geocoded_note)}</i>'
        )
    if r['Marker Text'].strip():
        parts.append(f'<b>Marker Text:</b> {escape(r["Marker Text"].strip())}')
    return '<br/><br/>'.join(parts)


# Pending markers get an orange pin so they read as "do not drive out for this
# yet" at a glance, without opening the popup. Google My Maps honors an
# IconStyle whose href points at its own hosted icon set.
STYLES = (
    '  <Style id="normal">\n'
    '    <IconStyle>\n'
    '      <Icon><href>http://maps.google.com/mapfiles/ms/icons/red-dot.png</href></Icon>\n'
    '    </IconStyle>\n'
    '  </Style>\n'
    '  <Style id="pending">\n'
    '    <IconStyle>\n'
    '      <color>ff00a5ff</color>\n'          # KML is aabbggrr -> orange
    '      <Icon><href>http://maps.google.com/mapfiles/ms/icons/orange-dot.png</href></Icon>\n'
    '    </IconStyle>\n'
    '  </Style>\n'
)


def placemark(r: dict, lon: str, lat: str, geocoded_note: str | None = None) -> str:
    pending = is_pending(r)
    name_prefix = '[PENDING] ' if pending else ''
    return (
        '  <Placemark>\n'
        f'    <name>{escape(name_prefix + r["name"])}</name>\n'
        f'    <styleUrl>#{"pending" if pending else "normal"}</styleUrl>\n'
        f'    <description><![CDATA[{desc(r, geocoded_note)}]]></description>\n'
        f'    <Point><coordinates>{lon},{lat},0</coordinates></Point>\n'
        '  </Placemark>'
    )


def write_geocoded_to_atlas(atlas_path: Path, updates: dict[str, tuple[float, float]]):
    """Update estimated:Latitude/estimated:Longitude for each {thc_id: (lat, lon)} pair.

    Reads, modifies in-memory, writes back preserving LF line endings.
    """
    with atlas_path.open(newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    header = rows[0]
    lat_i = header.index('estimated:Latitude')
    lon_i = header.index('estimated:Longitude')
    id_i = header.index('ref:US-TX:thc')
    n = 0
    for row in rows[1:]:
        thc_id = row[id_i]
        if thc_id in updates:
            lat, lon = updates[thc_id]
            row[lat_i] = f'{lat:.5f}'
            row[lon_i] = f'{lon:.5f}'
            n += 1
    with atlas_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerows(rows)
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--county', required=True, help='County name (e.g. "Tarrant")')
    p.add_argument('--atlas', default='atlas_db.csv', help='Path to atlas_db.csv')
    p.add_argument('--out-dir', default='unmapped markers', help='Output directory')
    p.add_argument('--no-write-coords', action='store_true',
                   help='Do not write geocoded coords back to atlas_db.csv')
    args = p.parse_args()

    atlas = Path(args.atlas).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    county = args.county
    kml_path = out_dir / f'{county}_unmapped_markers.kml'
    txt_path = out_dir / f'{county}_unmapped_no_coords.txt'

    # isActive=False marks a superseded or duplicate THC atlas record -- the same
    # physical marker is documented under another thc#, which usually already
    # has a ref:hmdb. Such a row has no ref:hmdb of its own, so it looks
    # unmapped and would send the user hunting for a marker already recorded.
    with atlas.open(newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f)
                if r['addr:county'] == county
                and not r['ref:hmdb'].strip()
                and r['isMissing'].strip().lower() != 'true'
                and r['isPrivate'].strip().lower() != 'true'
                and r['isActive'].strip().lower() != 'false']

    if not rows:
        print(f'No unmapped markers found for county "{county}".', file=sys.stderr)
        sys.exit(1)

    mapped = [r for r in rows if r['estimated:Latitude'].strip() and r['estimated:Longitude'].strip()]
    needs_coord = [r for r in rows if not (r['estimated:Latitude'].strip() and r['estimated:Longitude'].strip())]

    geocoded = []
    still_unmapped = []
    geocoded_updates: dict[str, tuple[float, float]] = {}

    for r in needs_coord:
        addr = r['addr:full'].strip()
        if addr and has_street_address(addr):
            try:
                result = geocode(addr, r['addr:city'].strip())
                time.sleep(1.1)  # Nominatim usage policy: ≤1 req/sec
                if result:
                    lat, lon, display = result
                    r['_geocoded_lat'] = lat
                    r['_geocoded_lon'] = lon
                    r['_geocoded_display'] = display
                    geocoded.append(r)
                    geocoded_updates[r['ref:US-TX:thc']] = (lat, lon)
                    print(f'  geocoded: THC {r["ref:US-TX:thc"]} {r["name"][:50]} -> {lat:.5f},{lon:.5f}')
                    continue
                else:
                    print(f'  NO RESULT: THC {r["ref:US-TX:thc"]} {addr}, {r["addr:city"]}')
            except Exception as e:
                print(f'  ERROR: THC {r["ref:US-TX:thc"]}: {e}')
        still_unmapped.append(r)

    placemarks = []
    for r in sorted(mapped, key=lambda x: x['name'].lower()):
        placemarks.append(placemark(r, r['estimated:Longitude'], r['estimated:Latitude']))
    for r in sorted(geocoded, key=lambda x: x['name'].lower()):
        placemarks.append(placemark(
            r,
            f'{r["_geocoded_lon"]:.5f}',
            f'{r["_geocoded_lat"]:.5f}',
            r['_geocoded_display'],
        ))

    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        '<Document>\n'
        f'  <name>{escape(county)} County — Unmapped Historical Markers</name>\n'
        f'  <description>THC markers in {escape(county)} County without an HMDB id (isMissing excluded). '
        f'{len(mapped)} with THC coords; {len(geocoded)} geocoded from address; '
        f'{len(still_unmapped)} omitted (no usable address). '
        f'Orange pins are isPending=True — the marker may not be installed yet.</description>\n'
        + STYLES
        + '\n'.join(placemarks)
        + '\n</Document>\n</kml>\n'
    )
    kml_path.write_text(kml, encoding='utf-8')

    with txt_path.open('w', encoding='utf-8') as f:
        f.write(f'{county} unmapped markers with NO usable address ({len(still_unmapped)}):\n\n')
        for r in sorted(still_unmapped, key=lambda x: x['name'].lower()):
            addr = ', '.join(b for b in [r['addr:full'].strip(), r['addr:city'].strip()] if b)
            f.write(f'  THC {r["ref:US-TX:thc"]}: {r["name"]}\n')
            if addr:
                f.write(f'    addr: {addr}\n')
            f.write(f'    {r["website"]}\n\n')

    print()
    print(f'KML: {kml_path}  ({len(mapped) + len(geocoded)} placemarks: '
          f'{len(mapped)} THC + {len(geocoded)} geocoded)')
    print(f'No-coord list: {txt_path}  ({len(still_unmapped)} markers)')

    if geocoded_updates and not args.no_write_coords:
        n = write_geocoded_to_atlas(atlas, geocoded_updates)
        print(f'Wrote {n} geocoded coord pairs back to {atlas}.')
    elif geocoded_updates and args.no_write_coords:
        print(f'(--no-write-coords set; {len(geocoded_updates)} geocoded coords NOT persisted to atlas)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Audit thc:Latitude/Longitude against the US Census Geocoder for unmapped
markers in a county. Flag any row with > THRESHOLD_MI miles of separation.

Uses the Census batch geocoder (free, no key, ~10k addresses per call):
    https://geocoding.geo.census.gov/geocoder/locations/addressbatch

Usage:
  python3 audit_coords.py --county Tarrant
"""
import argparse
import csv
import io
import math
import mimetypes
import sys
import urllib.request
from pathlib import Path
from uuid import uuid4

CENSUS_BATCH = 'https://geocoding.geo.census.gov/geocoder/locations/addressbatch'
BENCHMARK = 'Public_AR_Current'
THRESHOLD_MI = 0.5


def has_street_address(addr: str) -> bool:
    return any(c.isdigit() for c in addr)


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def encode_multipart(fields: dict, files: dict):
    """Build a multipart/form-data body and Content-Type header.

    fields: {name: str_value}
    files:  {name: (filename, bytes, mime)}
    """
    boundary = uuid4().hex
    lines = []
    for name, value in fields.items():
        lines.append(f'--{boundary}'.encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b'')
        lines.append(str(value).encode())
    for name, (filename, content, mime) in files.items():
        lines.append(f'--{boundary}'.encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        lines.append(f'Content-Type: {mime}'.encode())
        lines.append(b'')
        lines.append(content)
    lines.append(f'--{boundary}--'.encode())
    lines.append(b'')
    body = b'\r\n'.join(lines)
    content_type = f'multipart/form-data; boundary={boundary}'
    return body, content_type


def census_batch_geocode(rows: list[dict], timeout: int = 300) -> dict[str, tuple[float, float, str]]:
    """Return {unique_id: (lat, lon, matched_address)} for successfully matched rows."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    for r in rows:
        writer.writerow([
            r['ref:US-TX:thc'],
            r['addr:full'].strip(),
            r['addr:city'].strip(),
            'TX',
            '',
        ])
    body, content_type = encode_multipart(
        fields={'benchmark': BENCHMARK},
        files={'addressFile': ('input.csv', buf.getvalue().encode('utf-8'), 'text/csv')},
    )
    req = urllib.request.Request(
        CENSUS_BATCH, data=body,
        headers={'Content-Type': content_type, 'Accept': 'text/plain'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode('utf-8', errors='replace')

    results = {}
    # Output columns: id, input_address, match_indicator, match_type,
    # matched_address, lon_lat, tigerline_id, side
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < 6:
            continue
        uid = row[0]
        match_indicator = row[2]
        if match_indicator != 'Match':
            continue
        matched_address = row[4]
        coords = row[5]
        if not coords or ',' not in coords:
            continue
        lon_str, lat_str = coords.split(',', 1)
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            continue
        results[uid] = (lat, lon, matched_address)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--county', required=True)
    p.add_argument('--atlas', default='atlas_db.csv')
    p.add_argument('--out', default=None)
    p.add_argument('--threshold-mi', type=float, default=THRESHOLD_MI)
    args = p.parse_args()

    atlas = Path(args.atlas).resolve()
    out_path = Path(args.out) if args.out else Path('unmapped markers') / f'{args.county}_coord_audit_review.csv'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = out_path.resolve()

    with atlas.open(newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f)
                if r['addr:county'] == args.county
                and not r['ref:hmdb'].strip()
                and r['thc:Latitude'].strip()
                and r['thc:Longitude'].strip()
                and r['addr:full'].strip()
                and has_street_address(r['addr:full'])]

    print(f'Auditing {len(rows)} {args.county} unmapped markers '
          f'(have THC coord + street-level address)...')
    print(f'Submitting batch to Census Geocoder (benchmark={BENCHMARK})...')

    matches = census_batch_geocode(rows)
    print(f'  matched: {len(matches)}/{len(rows)}')

    flagged = []
    unmatched = []
    for r in rows:
        uid = r['ref:US-TX:thc']
        if uid not in matches:
            unmatched.append(r)
            continue
        g_lat, g_lon, display = matches[uid]
        thc_lat = float(r['thc:Latitude'])
        thc_lon = float(r['thc:Longitude'])
        dist = haversine_miles(thc_lat, thc_lon, g_lat, g_lon)
        if dist > args.threshold_mi:
            flagged.append((r, g_lat, g_lon, display, dist))

    fieldnames = [
        'ref:US-TX:thc', 'name', 'distance_miles',
        'addr:full', 'addr:city',
        'thc:Latitude', 'thc:Longitude',
        'geocoded:Latitude', 'geocoded:Longitude',
        'geocoded:matched_address', 'website',
    ]
    with out_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator='\n')
        w.writeheader()
        for r, g_lat, g_lon, display, dist in sorted(flagged, key=lambda x: -x[4]):
            w.writerow({
                'ref:US-TX:thc': r['ref:US-TX:thc'],
                'name': r['name'],
                'distance_miles': f'{dist:.2f}',
                'addr:full': r['addr:full'],
                'addr:city': r['addr:city'],
                'thc:Latitude': r['thc:Latitude'],
                'thc:Longitude': r['thc:Longitude'],
                'geocoded:Latitude': f'{g_lat:.5f}',
                'geocoded:Longitude': f'{g_lon:.5f}',
                'geocoded:matched_address': display,
                'website': r['website'],
            })

    within = len(rows) - len(unmatched) - len(flagged)
    print()
    print(f'Audited:       {len(rows)}')
    print(f'  within {args.threshold_mi} mi: {within}')
    print(f'  flagged (> {args.threshold_mi} mi): {len(flagged)}')
    print(f'  unmatched (Census could not geocode): {len(unmatched)}')
    print(f'Review file:   {out_path}')

    if unmatched:
        print()
        print('Unmatched (no Census result):')
        for r in unmatched:
            print(f'  THC {r["ref:US-TX:thc"]:>6}: {r["addr:full"]}, {r["addr:city"]}')


if __name__ == '__main__':
    main()

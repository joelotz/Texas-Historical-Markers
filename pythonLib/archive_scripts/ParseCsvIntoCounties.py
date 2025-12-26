#!/usr/bin/env python3
"""
THC Route Proximity Mapper
--------------------------

Reads a KML route and a Texas Historical Marker CSV, then finds markers located
within a given radius of the route. Can show all markers or only unmapped ones,
and supports map generation, CSV export, and GeoJSON/KML output.

Default Run (minimal):
    python MarkersAlongTrack.py --track track.kml --data data.csv
        radius: 5 miles (default)
        output: near_route_map_<tag>_<radius>mi.html

Required:
  --track FILE            Input KML route file
  --data FILE             Texas Historical Marker CSV dataset

Optional:
  --radius N              Search radius in miles (default: 5)
  --unmapped              Include only markers with missing HMDB reference
  --all                   Include mapped + unmapped (overrides --unmapped)
  --export-csv            Export matched markers to CSV
  --geojson               Export combined route + markers as GeoJSON
  --kml                   Export Google Earth compatible KML
  --open                  Open generated HTML map in browser

Examples:
  python MarkersAlongTrack.py --track track01.kml --data data.csv
  python MarkersAlongTrack.py --track route.kml --data data.csv --unmapped
  python MarkersAlongTrack.py --track trip.kml --data data.csv --radius 10 --export-csv
  python MarkersAlongTrack.py --track trip.kml --data data.csv --geojson --kml --open

Output Files:
  near_route_map_<tag>_<radius>mi.html
  near_route_<tag>_<radius>mi.csv                (if --export-csv)
  combined_route_markers_<tag>.geojso_
"""

import os
import argparse
import pandas as pd
import json


# ====================== Filtering Function ======================

def load_filtered(input_file):
    df = pd.read_csv(input_file, low_memory=False)
    base = df[df["ref:hmdb"].isna() | (df["ref:hmdb"].astype(str).str.strip() == "")]
    return base[
        ~((base.get("isMissing") == True) | (base.get("isPrivate") == True))
    ]


# ======================== Export Helpers =========================

def export_counties(df, outdir):
    os.makedirs(outdir, exist_ok=True)
    summary = {}

    for county, group in df.groupby("addr:county"):
        safe = str(county).replace(" ", "_").replace("/", "-")
        outfile = os.path.join(outdir, f"{safe}.csv")
        group.to_csv(outfile, index=False)
        summary[county] = len(group)
        print(f"✔ Saved {outfile} ({len(group)} rows)")

    return summary


def export_single_county(df, county, outdir):
    os.makedirs(outdir, exist_ok=True)
    match = df[df["addr:county"].str.lower() == county.lower()]

    if match.empty:
        print(f"⚠ No markers found for county: {county}")
        return None

    safe = county.replace(" ", "_").replace("/", "-")
    outfile = os.path.join(outdir, f"{safe}.csv")
    match.to_csv(outfile, index=False)
    print(f"✔ Exported county only → {outfile} ({len(match)} rows)")
    return {county: len(match)}


def merge_all(df, filename):
    df.to_csv(filename, index=False)
    print(f"✔ Merged master file → {filename} ({len(df)} total rows)")


def write_summary_json(summary, filename):
    with open(filename, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"✔ Summary written → {filename}")


def print_stats_table(summary):
    print("\n===== County Marker Counts =====")
    for county, count in sorted(summary.items(), key=lambda x: x[1], reverse=True):
        print(f"{county:<25} {count}")
    print("================================\n")


# ============================ CLI ===============================

def cli():
    parser = argparse.ArgumentParser(description="Export Texas Historical Marker datasets.")

    parser.add_argument("-i", "--input", default="data.csv")
    parser.add_argument("-o", "--output", default="UnmappedMarkersPerCounty")
    parser.add_argument("--county", help="Export only one county (ex: 'Denton')")
    parser.add_argument("--merge", metavar="FILE", help="Merge all filtered results into one file")
    parser.add_argument("--summary-json", metavar="FILE", help="Write summary counts as JSON")
    parser.add_argument("--stats", action="store_true", help="Display a table of counts per county")
    parser.add_argument("--show-docs", action="store_true", help="Print documentation and exit")

    args = parser.parse_args()

    if args.show_docs:
        print(__doc__)
        return

    df = load_filtered(args.input)

    # Single county mode (no batch export)
    if args.county:
        summary = export_single_county(df, args.county, args.output)
        if summary and args.stats: print_stats_table(summary)
        if summary and args.summary_json: write_summary_json(summary, args.summary_json)
        return

    # Normal multi–county export
    summary = export_counties(df, args.output)

    if args.merge: merge_all(df, args.merge)
    if args.stats: print_stats_table(summary)
    if args.summary_json: write_summary_json(summary, args.summary_json)


if __name__ == "__main__":
    cli()

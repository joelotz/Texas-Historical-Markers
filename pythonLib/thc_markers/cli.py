#!/usr/bin/env python3
"""
THC Markers Toolkit - Unified CLI
---------------------------------

Commands:
    thc counties   → work with county-based exports (per-county CSV/merge/stats)
    thc route      → map markers along a KML route (HTML/CSV/GeoJSON/KML)
    thc docs       → show documentation for either tool

Examples:
    thc counties --input data.csv --stats
    thc counties --county Denton --summary-json summary.json
    thc route --track trip.kml --data data.csv --unmapped --open
    thc docs counties
    thc docs route
"""

import argparse
from . import counties_cli
from . import route_cli


# ------------------- Subcommand Implementations ------------------- #

def run_counties(args):
    df = counties_cli.load_filtered(args.input)

    # Single county mode
    if args.county:
        summary = counties_cli.export_single_county(df, args.county, args.output)
        if summary and args.stats:
            counties_cli.print_stats_table(summary)
        if summary and args.summary_json:
            counties_cli.write_summary_json(summary, args.summary_json)
        return

    # Multi-county export
    summary = counties_cli.export_counties(df, args.output)
    if args.merge:
        counties_cli.merge_all(df, args.merge)
    if args.stats:
        counties_cli.print_stats_table(summary)
    if args.summary_json:
        counties_cli.write_summary_json(summary, args.summary_json)


def run_route(args):
    route_cli.run_with_args(
        track_file=args.track,
        data_file=args.data,
        radius=args.radius,
        unmapped=args.unmapped,
        include_all=args.all,
        export_csv=args.export_csv,
        geojson=args.geojson,
        kml=args.kml,
        open_map=args.open,
    )


def run_docs(args):
    if args.tool == "counties":
        print(counties_cli.__doc__)
    elif args.tool == "route":
        print(route_cli.__doc__)
    else:
        print("Invalid tool.")


# ---------------------------- CLI Root ---------------------------- #

def main():
    parser = argparse.ArgumentParser(
        prog="thc",
        description="Texas Historical Markers Toolkit (Unified CLI)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # counties
    c = sub.add_parser("counties", help="Work with county-based exports")
    c.add_argument("-i", "--input", default="data.csv")
    c.add_argument("-o", "--output", default="UnmappedMarkersPerCounty")
    c.add_argument("--county", help="Export just one county")
    c.add_argument("--merge", metavar="FILE", help="Merge all into one CSV")
    c.add_argument("--summary-json", metavar="FILE", help="Output summary JSON")
    c.add_argument("--stats", action="store_true")
    c.set_defaults(func=run_counties)

    # route
    r = sub.add_parser("route", help="Find markers near a KML route")
    r.add_argument("--track", required=True, help="Track KML file")
    r.add_argument("--data", required=True, help="Marker CSV data")
    r.add_argument("--radius", type=float, default=5)
    r.add_argument("--unmapped", action="store_true")
    r.add_argument("--all", action="store_true")
    r.add_argument("--export-csv", action="store_true")
    r.add_argument("--geojson", action="store_true")
    r.add_argument("--kml", action="store_true")
    r.add_argument("--open", action="store_true")
    r.set_defaults(func=run_route)

    # docs
    d = sub.add_parser("docs", help="Show documentation for commands")
    d.add_argument("tool", choices=["counties", "route"])
    d.set_defaults(func=run_docs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

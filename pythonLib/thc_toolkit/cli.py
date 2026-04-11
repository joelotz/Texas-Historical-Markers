#!/usr/bin/env python3
"""
THC Markers Toolkit - Unified CLI
---------------------------------

Commands:
    thc counties   → export county-based CSVs (supports --simple)
    thc route      → KML route + proximity mapping tools
    thc docs       → show docs for subcommands

Examples:
    thc counties --input ../atlas_db.csv --stats
    thc counties --simple --merge all.csv
    thc counties --county Denton --simple
    thc route --track ../scripts/test.kml --data ../atlas_db.csv --unmapped --openmap
"""

import argparse
from . import counties_cli
from . import route_cli
from . import map_cli
from .utils import convert_hmdb_csv

# ------------------- Subcommand Implementations ------------------- #

def run_counties(args):
    input_path = counties_cli.resolve_input_path(args.input)
    df = counties_cli.load_filtered(input_path)

    # --- single county mode ---
    if args.county:
        summary = counties_cli.export_single_county(df, args.county, args.output, simple=args.simple)
        if summary and args.stats:
            counties_cli.print_stats_table(summary)
        if summary and args.summary_json:
            counties_cli.write_summary_json(summary, args.summary_json)
        return

    # --- multi-county export ---
    summary = counties_cli.export_counties(df, args.output, simple=args.simple)

    if args.merge:
        counties_cli.merge_all(df, args.merge, simple=args.simple)
    if args.stats:
        counties_cli.print_stats_table(summary)
    if args.summary_json:
        counties_cli.write_summary_json(summary, args.summary_json)


def run_route(args):
    only_mapped = getattr(args, "only_mapped", False)
    route_cli.run_with_args(
        track=args.track,
        data=args.data,
        radius=args.radius,
        unmapped=args.unmapped,
        only_mapped=only_mapped,
        csv=args.csv,
        csv_simple=(args.simple or getattr(args, "csv_simple", False)),
        geojson=args.geojson,
        kml=args.kml,
        openmap=args.openmap
    )

def run_docs(args):
    if args.tool == "counties":
        print(counties_cli.__doc__)
    elif args.tool == "route":
        print(route_cli.__doc__)
    elif args.tool == "map":
        print(map_cli.__doc__)
    else:
        print("Invalid tool.")

def run_viewcsv(args):
    import pandas as pd
    import shutil
    from .utils import (
        viewcsv_pretty,
        viewcsv_head, viewcsv_tail,
        viewcsv_search, viewcsv_interactive
    )

    df = None

    # 1. SEARCH
    if args.search:
        df = viewcsv_search(args.file, args.search)

    # 2. HEAD/TAIL (override search result if provided)
    if args.head:
        df = viewcsv_head(args.file, args.head)

    if args.tail:
        df = viewcsv_tail(args.file, args.tail)

    # 3. LOAD FILE if df not already made
    if df is None:
        df = pd.read_csv(args.file)

    # 4. INTERACTIVE VIEW
    if args.interactive:
        viewcsv_interactive(df)
        return

    # 5. OUTPUT MODE
    if args.raw:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", shutil.get_terminal_size().columns)
        print(df.to_string(index=False))
    else:
        tmp = "_thc_view_temp.csv"
        df.to_csv(tmp, index=False)
        viewcsv_pretty(tmp)

def run_map(args):
    map_cli.run_with_args(args)


# ---------------------------- CLI Root ---------------------------- #

def main():
    parser = argparse.ArgumentParser(
        prog="thc",
        description="Texas Historical Markers Toolkit (Unified CLI)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -------- counties CLI --------
    c = sub.add_parser("counties", help="Export THC markers by county")
    c.add_argument(
        "-i",
        "--input",
        default=None,
        help="Path to marker CSV (auto-detects common paths when omitted)",
    )
    c.add_argument("-o", "--output", default="UnmappedMarkersPerCounty")
    c.add_argument("--county", help="single county only, case-insensitive")
    c.add_argument("--merge", metavar="FILE", help="export a merged CSV file")
    c.add_argument("--summary-json", metavar="FILE")
    c.add_argument("--stats", action="store_true")
    c.add_argument("--simple", action="store_true",
                   help="export only core columns (simple CSV mode)")
    c.set_defaults(func=run_counties)

    # -------- route CLI wrapper (optional sync with route_cli next)--------
    r = sub.add_parser("route", help="Find markers along a GPS/KML route")
    r.add_argument("--track", required=True)
    r.add_argument("--data", required=True)
    r.add_argument("--radius", type=float, default=5)
    group = r.add_mutually_exclusive_group()
    group.add_argument("--unmapped", action="store_true", help="show only unmapped markers")
    group.add_argument("--only_mapped", action="store_true", help="show only mapped markers")
    r.add_argument("--csv", action="store_true")
    r.add_argument("--simple", action="store_true", help="export simplified route CSV")
    r.add_argument("--csv_simple", action="store_true", help="alias for --simple")
    r.add_argument("--geojson", action="store_true")
    r.add_argument("--kml", action="store_true")
    r.add_argument("--openmap", action="store_true")
    r.set_defaults(func=run_route)

    # -------- docs --------
    d = sub.add_parser("docs", help="Show documentation for a module")
    d.add_argument("tool", choices=["counties", "route", "map"])
    d.set_defaults(func=run_docs)

    # -------- CSV Viewer --------
    v = sub.add_parser("viewcsv", help="Display a CSV in the terminal")
    v.add_argument("file", help="CSV file to display")
    v.add_argument("--raw", action="store_true", help="Default is pretty view, use raw viewer instead")
    v.add_argument("--head", type=int, metavar="N", help="Show first N rows only")
    v.add_argument("--tail", type=int, metavar="N", help="Show last N rows only")
    v.add_argument("--search", metavar="TEXT", help="Filter to rows where name contains TEXT (case-insensitive)")
    v.add_argument("--interactive", action="store_true", help="Interactive scrollable view (rich table)")
    v.set_defaults(func=run_viewcsv)

    # -------- HMDB Converter --------
    h = sub.add_parser("convertHMDB", help="Convert HMDB CSV → THC format")
    h.add_argument("--input", '-i', required=True)
    h.add_argument("--output", '-o', required=True)
    h.set_defaults(func=lambda a: convert_hmdb_csv(a.input, a.output))

    # -------- map CLI --------
    m = sub.add_parser("map", help="Map THC markers by county/city")
    m.add_argument("--data", required=True)
    m.add_argument("--county")
    m.add_argument("--city")
    m.add_argument("--unmapped", action="store_true")
    m.add_argument("--csv", action="store_true")
    m.add_argument(
        "--simple",
        action="store_true",
        help="write markers_<tag>_simple.csv (independent of --csv)",
    )
    m.add_argument("--geojson", action="store_true")
    m.add_argument("--kml", action="store_true")
    m.add_argument("--openmap", action="store_true")
    m.set_defaults(func=run_map)


    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
THC Unmapped Marker Export Tool — Enhanced w/ SIMPLE mode + Safe Integer Output
-----------------------------------------------------------------------------

Exports Texas Historical Marker datasets per county OR merged.  
Supports simplified CSVs via `--simple`.

All output CSVs — simple or full — guarantee:
    ref:US-TX:thc → Int64
    ref:hmdb      → Int64
    OsmNodeID     → Int64

Usage Examples:
    python counties_cli.py
    python counties_cli.py --county Denton
    python counties_cli.py --merge all.csv --simple
    python counties_cli.py --simple --stats
"""

import os
import argparse
import pandas as pd
import json

# Columns used when --simple is applied
simple_fields = [
    "ref:US-TX:thc", "ref:hmdb", "OsmNodeID", "name",
    "website", "memorial:website", "addr:city", "addr:county",
    "thc:Latitude", "thc:Longitude"
]

# These must always be exported as integers
int_fields = ["ref:US-TX:thc", "ref:hmdb", "OsmNodeID"]


# ====================== Core Load & Filtering ======================

def load_filtered(input_file):
    df = pd.read_csv(input_file, low_memory=False)

    # unmapped detection logic
    hmdb = df["ref:hmdb"].astype(str).str.strip().str.lower()
    base = df[hmdb.isin(["", "nan", "none"]) | df["ref:hmdb"].isna()].copy()

    # drop private/missing if present
    return base[
        ~((base.get("isMissing") == True) | (base.get("isPrivate") == True))
    ].copy()


# ====================== Transformation Helpers ======================

def enforce_integer_safe(df):
    """Guarantee int_fields are Int64 type in exported files."""
    for col in int_fields:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        else:
            df[col] = pd.Series([pd.NA] * len(df), dtype="Int64")
    return df


def apply_simple(df):
    """Return simplified dataframe cleanly ordered."""
    for col in simple_fields:
        if col not in df.columns:
            df[col] = ""
    df = df[simple_fields].copy()
    return enforce_integer_safe(df)   # ← still integer correct


# ====================== Export Methods ======================

def export_counties(df, outdir, simple=False):
    os.makedirs(outdir, exist_ok=True)
    summary = {}

    for county, group in df.groupby("addr:county"):
        safe = str(county).replace(" ", "_").replace("/", "-")
        outfile = os.path.join(outdir, f"{safe}.csv")

        out = apply_simple(group) if simple else enforce_integer_safe(group.copy())
        out.to_csv(outfile, index=False)

        summary[county] = len(out)
        print(f"✔ Saved {outfile} ({len(out)} rows)")
    return summary


def export_single_county(df, county, outdir, simple=False):
    os.makedirs(outdir, exist_ok=True)
    subset = df[df["addr:county"].str.lower() == county.lower()].copy()

    if subset.empty:
        print(f"⚠ No markers found in {county}")
        return None

    safe = county.replace(" ", "_").replace("/", "-")
    outfile = os.path.join(outdir, f"{safe}.csv")

    out = apply_simple(subset) if simple else enforce_integer_safe(subset)
    out.to_csv(outfile, index=False)

    print(f"✔ Exported → {outfile} ({len(out)} rows)")
    return {county: len(out)}


def merge_all(df, filename, simple=False):
    out = apply_simple(df) if simple else enforce_integer_safe(df.copy())
    out.to_csv(filename, index=False)
    print(f"✔ Merged master → {filename} ({len(out)} rows)")


# ====================== Summary ======================

def write_summary_json(summary, filename):
    with open(filename, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"✔ Summary written → {filename}")


def print_stats_table(summary):
    print("\n===== County Marker Counts =====")
    for county, count in sorted(summary.items(), key=lambda x: x[1], reverse=True):
        print(f"{county:<25} {count}")
    print("================================\n")


# ====================== CLI ======================

def cli():
    p = argparse.ArgumentParser(description="Export THC marker datasets")
    p.add_argument("-i","--input", default="data.csv")
    p.add_argument("-o","--output", default="UnmappedMarkersPerCounty")
    p.add_argument("--county")
    p.add_argument("--merge", metavar="FILE")
    p.add_argument("--summary-json", metavar="FILE")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--simple", action="store_true", help="export only core fields")
    p.add_argument("--show-docs", action="store_true")

    args = p.parse_args()
    if args.show_docs:
        print(__doc__)
        return

    df = load_filtered(args.input)

    # single county mode
    if args.county:
        summary = export_single_county(df, args.county, args.output, args.simple)
        if summary and args.stats: print_stats_table(summary)
        if summary and args.summary_json: write_summary_json(summary, args.summary_json)
        return

    # all counties
    summary = export_counties(df, args.output, args.simple)

    if args.merge: merge_all(df, args.merge, args.simple)
    if args.stats: print_stats_table(summary)
    if args.summary_json: write_summary_json(summary, args.summary_json)


def main():
    cli()

if __name__ == "__main__":
    main()

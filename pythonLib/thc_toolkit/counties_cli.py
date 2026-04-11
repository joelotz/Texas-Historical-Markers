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
try:
    from .utils import (
        require_columns,
        normalize_match_key,
        normalize_match_series,
        parse_bool_series,
        coerce_nullable_int_series,
        assert_no_duplicate_ids,
    )
except ImportError:  # pragma: no cover - compatibility for direct script execution
    from utils import (  # type: ignore
        require_columns,
        normalize_match_key,
        normalize_match_series,
        parse_bool_series,
        coerce_nullable_int_series,
        assert_no_duplicate_ids,
    )

# Columns used when --simple is applied
simple_fields = [
    "ref:US-TX:thc", "ref:hmdb", "OsmNodeID", "name",
    "website", "memorial:website", "addr:city", "addr:county",
    "thc:Latitude", "thc:Longitude"
]

# These must always be exported as integers
int_fields = ["ref:US-TX:thc", "ref:hmdb", "OsmNodeID"]
default_input_candidates = [
    "data.csv",
    "atlas_db.csv",
    "../atlas_db.csv",
    "scripts/data.csv",
    "../scripts/data.csv",
]


# ====================== Core Load & Filtering ======================

def load_filtered(input_file):
    df = pd.read_csv(input_file, low_memory=False)
    require_columns(df, ["ref:hmdb", "isMissing", "isPrivate"], context="counties input")

    # unmapped detection logic
    hmdb = df["ref:hmdb"].astype(str).str.strip().str.casefold()
    is_unmapped = hmdb.isin(["", "nan", "none", "null", "na"]) | df["ref:hmdb"].isna()
    is_missing = parse_bool_series(df["isMissing"], "isMissing", context="counties input", na_value=False)
    is_private = parse_bool_series(df["isPrivate"], "isPrivate", context="counties input", na_value=False)
    base = df[is_unmapped & ~is_missing & ~is_private].copy()

    assert_no_duplicate_ids(base, ["ref:US-TX:thc", "ref:hmdb"], context="counties filtered input")
    return base


def resolve_input_path(input_file=None):
    """Resolve atlas CSV when --input is omitted."""
    if input_file:
        return input_file

    for candidate in default_input_candidates:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "No default input CSV found. Provide --input PATH "
        "(tried: data.csv, atlas_db.csv, ../atlas_db.csv, scripts/data.csv, ../scripts/data.csv)."
    )


# ====================== Transformation Helpers ======================

def enforce_integer_safe(df):
    """Guarantee int_fields are Int64 type in exported files."""
    for col in int_fields:
        if col in df.columns:
            df[col] = coerce_nullable_int_series(df[col], col, context="counties export")
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
    require_columns(df, ["addr:county"], context="counties export input")
    assert_no_duplicate_ids(df, ["ref:US-TX:thc", "ref:hmdb"], context="counties export input")
    os.makedirs(outdir, exist_ok=True)
    summary = {}
    normalized = normalize_match_series(df["addr:county"])
    missing_county = normalized.eq("").sum()
    if missing_county:
        print(f"⚠ {missing_county} rows missing addr:county; exporting as Unknown.csv")

    working = df.copy()
    working["__county_key"] = normalized.mask(normalized.ne(""), normalized)
    working.loc[working["__county_key"] == "", "__county_key"] = "__unknown__"

    for county_key, group in working.groupby("__county_key", dropna=False):
        if county_key == "__unknown__":
            county_label = "Unknown"
        else:
            labels = group["addr:county"].dropna().astype(str).str.strip()
            county_label = labels.iloc[0] if not labels.empty else str(county_key)
        safe = str(county_label).replace(" ", "_").replace("/", "-")
        outfile = os.path.join(outdir, f"{safe}.csv")
        export_group = group.drop(columns=["__county_key"])
        out = apply_simple(export_group) if simple else enforce_integer_safe(export_group.copy())
        out.to_csv(outfile, index=False)

        summary[county_label] = len(out)
        print(f"✔ Saved {outfile} ({len(out)} rows)")
    return summary


def export_single_county(df, county, outdir, simple=False):
    require_columns(df, ["addr:county"], context="single county export input")
    assert_no_duplicate_ids(df, ["ref:US-TX:thc", "ref:hmdb"], context="single county export input")
    os.makedirs(outdir, exist_ok=True)
    county_key = normalize_match_key(county)
    subset = df[normalize_match_series(df["addr:county"]).eq(county_key)].copy()

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
    assert_no_duplicate_ids(df, ["ref:US-TX:thc", "ref:hmdb"], context="counties merge input")
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
    p.add_argument(
        "-i",
        "--input",
        default=None,
        help="Path to marker CSV (auto-detects common paths when omitted)",
    )
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

    df = load_filtered(resolve_input_path(args.input))

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

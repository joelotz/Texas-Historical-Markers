#!/usr/bin/env python3
"""
THC OSM Integration Toolkit CLI
-------------------------------

Command-line utility for reading, converting, and synchronizing Texas Historical
Commission marker data with OpenStreetMap/JOSM. Wraps atlas helper functions
into a subcommand-based interface.

Usage Examples:
    python atlas_cli.py load --file data.csv
    python atlas_cli.py create-nodes --csv atlas.csv --out nodes.json
    python atlas_cli.py push-josm --nodes nodes.json
    python atlas_cli.py find-missing --csv atlas.csv --geo extract.geojson
    python atlas_cli.py update-isOSM --csv atlas.csv --nodes nodes.json --out new.csv

Workflow:
    Import atlas → create nodes → push to JOSM → update atlas flags → save results
"""

import argparse
import requests
import pandas as pd
from datetime import datetime
import json
try:
    from .utils import require_columns, assert_no_duplicate_ids, coerce_nullable_int_series
except ImportError:  # pragma: no cover - compatibility for direct script execution
    from utils import require_columns, assert_no_duplicate_ids, coerce_nullable_int_series  # type: ignore


def _normalize_scalar(value):
    """Convert pandas/numpy scalar NA values into JSON-safe Python values."""
    if pd.isna(value):
        return None
    return value


# ---------- Core Functions ---------- #

def read_atlas(filename):
    types = {'ref:US-TX:thc':'Int32','ref:hmdb':'Int32','start_date':'Int32',
             'UTM Easting':'Int32','UTM Northing':'Int32','UTM Zone':'Int16',
             'isTHC':'boolean','isHMDB':'boolean','isOSM':'boolean','isMissing':'boolean',
             'isPending':'boolean','Recorded Texas Historic Landmark':'boolean',
             'Private Property':'boolean','inGoogle':'boolean'}

    return pd.read_csv(filename, dtype=types, low_memory=False)


def create_nodes(df):
    require_columns(
        df,
        [
            "name",
            "ref:US-TX:thc",
            "ref:hmdb",
            "website",
            "hmdb:Latitude",
            "hmdb:Longitude",
        ],
        context="create_nodes input",
    )
    assert_no_duplicate_ids(df, ["ref:US-TX:thc", "ref:hmdb"], context="create_nodes input")
    thc_ref = coerce_nullable_int_series(
        df["ref:US-TX:thc"], "ref:US-TX:thc", context="create_nodes input"
    )
    hmdb_ref = coerce_nullable_int_series(
        df["ref:hmdb"], "ref:hmdb", context="create_nodes input"
    )
    nodes = []
    row_errors = []

    for index, row in df.iterrows():
        try:
            lat = pd.to_numeric(pd.Series([row["hmdb:Latitude"]]), errors="coerce").iloc[0]
            lon = pd.to_numeric(pd.Series([row["hmdb:Longitude"]]), errors="coerce").iloc[0]
            if pd.isna(lat) or pd.isna(lon):
                row_errors.append(f"row {index}: invalid hmdb:Latitude/hmdb:Longitude")
                continue

            row_thc = thc_ref.iloc[index]
            row_hmdb = hmdb_ref.iloc[index]
            tags = {
                "name": _normalize_scalar(row["name"]),
                "historic": "memorial",
                "memorial": "plaque",
                "material": "aluminium",
                "support": "pole",
                "operator": "Texas Historical Commission",
                "operator:wikidata": "Q2397965",
                "thc:designation": "Historical Marker",
                "ref:US-TX:thc": int(row_thc) if pd.notna(row_thc) else None,
                "ref:hmdb": int(row_hmdb) if pd.notna(row_hmdb) else None,
                "source:website": _normalize_scalar(row["website"]),
            }
            if pd.notna(row_hmdb):
                tags["memorial:website"] = f"https://www.hmdb.org/m.asp?m={int(row_hmdb)}"
            if "start_date" in df.columns and pd.notna(row.get("start_date")):
                tags["start_date"] = _normalize_scalar(row["start_date"])

            nodes.append({"lat": float(lat),
                          "lon": float(lon),
                          "tags": tags})

        except Exception as e:
            row_errors.append(f"row {index}: {e}")

    if row_errors:
        sample = "; ".join(row_errors[:5])
        raise ValueError(f"create_nodes input has invalid rows: {sample}")

    return nodes


def push2josm(nodes):
    josm_url = "http://localhost:8111/add_node"
    added_refs = []
    count = 0

    for node in nodes:
        clean_tags = {
            k: v for k, v in node["tags"].items()
            if v is not None and not (isinstance(v, str) and v.strip() == "")
        }
        tag_str = "|".join(f"{k}={v}" for k, v in clean_tags.items())
        params = {"lat": node["lat"], "lon": node["lon"], "addtags": tag_str}

        r = requests.get(josm_url, params=params)
        if r.status_code == 200:
            added_refs.append(node["tags"]["ref:US-TX:thc"])
            count += 1
        else:
            print(f"[FAIL] Node at {node['lat']},{node['lon']} ({r.status_code})")

    print(f"[OK] Pushed {count} nodes to JOSM")
    return added_refs


def write2csv(df, filename, date=False):
    if date:
        filename = f"./file_backup/{datetime.now():%Y%m%d}_{filename}"

    df.to_csv(filename, index=False)
    print(f"[OK] Saved → {filename}")


def find_missing_osm(atlas, geojson):
    require_columns(atlas, ["ref:US-TX:thc"], context="atlas")
    assert_no_duplicate_ids(atlas, ["ref:US-TX:thc"], context="atlas")
    with open(geojson,'r') as f:
        data = json.load(f)
    osm_ref_values = [
        str(f["properties"]["ref:US-TX:thc"]).strip()
        for f in data.get("features", [])
        if "ref:US-TX:thc" in f.get("properties", {})
    ]
    counts = pd.Series(osm_ref_values).value_counts()
    dupes = set(counts[counts > 1].index.tolist())
    if dupes:
        sample = ", ".join(repr(v) for v in sorted(dupes)[:5])
        raise ValueError(f"geojson has duplicate values in ref:US-TX:thc: {sample}")

    osm_refs = {int(v) for v in osm_ref_values if v}

    atlas_refs = set(atlas["ref:US-TX:thc"].dropna().astype(int))
    missing = sorted(atlas_refs - osm_refs)

    print(f"[INFO] Missing markers in OSM: {len(missing)}")
    return missing


def update_isOSM(updated_refs, atlas):
    require_columns(atlas, ["ref:US-TX:thc", "isOSM"], context="atlas")
    before = atlas["isOSM"].sum()
    atlas.loc[atlas["ref:US-TX:thc"].isin(updated_refs), "isOSM"] = True
    after = atlas["isOSM"].sum()

    print(f"[OK] Updated {after-before} markers as OSM-present")
    return atlas


# ---------- CLI Entry ---------- #

def main():
    parser = argparse.ArgumentParser(description="THC OSM Integration CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # read atlas
    load = sub.add_parser("load", help="Load and print atlas summary")
    load.add_argument("--file", required=True)

    # make nodes
    create = sub.add_parser("create-nodes", help="Convert atlas CSV → nodes.json")
    create.add_argument("--csv", required=True)
    create.add_argument("--out", default="nodes.json")

    # push to JOSM
    push = sub.add_parser("push-josm", help="Push nodes into JOSM remote control")
    push.add_argument("--nodes", required=True)

    # find missing
    fm = sub.add_parser("find-missing", help="Compare atlas against OSM GeoJSON")
    fm.add_argument("--csv", required=True)
    fm.add_argument("--geo", required=True)

    # update atlas isOSM flag
    update = sub.add_parser("update-isOSM", help="Flag markers as present in OSM")
    update.add_argument("--csv", required=True)
    update.add_argument("--nodes", required=True)
    update.add_argument("--out", required=True)

    args = parser.parse_args()


    # Commands
    if args.cmd == "load":
        atlas = read_atlas(args.file)
        print(atlas.head())
        print(f"[INFO] rows: {len(atlas)}")

    elif args.cmd == "create-nodes":
        df = read_atlas(args.csv)
        nodes = create_nodes(df)
        with open(args.out,"w") as f: json.dump(nodes,f,indent=2)
        print(f"[OK] Generated {len(nodes)} nodes → {args.out}")

    elif args.cmd == "push-josm":
        nodes = json.load(open(args.nodes))
        refs = push2josm(nodes)
        print("[INFO] Returned ref list:", refs)

    elif args.cmd == "find-missing":
        atlas = read_atlas(args.csv)
        missing = find_missing_osm(atlas,args.geo)
        print(missing)

    elif args.cmd == "update-isOSM":
        atlas = read_atlas(args.csv)
        refs = [n["tags"]["ref:US-TX:thc"] for n in json.load(open(args.nodes))]
        updated = update_isOSM(refs, atlas)
        write2csv(updated, args.out)

if __name__ == "__main__":
    main()

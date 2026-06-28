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
import time

try:
    from .utils import (
        require_columns,
        assert_no_duplicate_ids,
        coerce_nullable_int_series,
        filter_hmdb_missing_osm,
    )
    from . import osm_dedup, osm_sync, osm_refix, osm_refix_direct
except ImportError:  # pragma: no cover - compatibility for direct script execution
    from utils import (
        require_columns,
        assert_no_duplicate_ids,
        coerce_nullable_int_series,
        filter_hmdb_missing_osm,
    )  # type: ignore
    import osm_dedup  # type: ignore
    import osm_sync  # type: ignore
    import osm_refix  # type: ignore
    import osm_refix_direct  # type: ignore


def _normalize_scalar(value):
    """Convert pandas/numpy scalar NA values into JSON-safe Python values."""
    if pd.isna(value):
        return None
    return value


# ---------- Core Functions ---------- #


def read_atlas(filename):
    types = {
        "ref:US-TX:thc": "Int32",
        "ref:hmdb": "Int32",
        "OsmNodeID": "Int64",
        "start_date": "Int32",
        "UTM Easting": "Int32",
        "UTM Northing": "Int32",
        "UTM Zone": "Int16",
        "isTHC": "boolean",
        "isHMDB": "boolean",
        "isOSM": "boolean",
        "isMissing": "boolean",
        "isPending": "boolean",
        "Recorded Texas Historic Landmark": "boolean",
        "Private Property": "boolean",
        "inGoogle": "boolean",
    }

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
    assert_no_duplicate_ids(
        df, ["ref:US-TX:thc", "ref:hmdb"], context="create_nodes input"
    )
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
            lat = pd.to_numeric(
                pd.Series([row["hmdb:Latitude"]]), errors="coerce"
            ).iloc[0]
            lon = pd.to_numeric(
                pd.Series([row["hmdb:Longitude"]]), errors="coerce"
            ).iloc[0]
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
                "operator": "Texas Historical Commission",
                "operator:wikidata": "Q2397965",
                "ref:US-TX:thc": int(row_thc) if pd.notna(row_thc) else None,
                "ref:hmdb": int(row_hmdb) if pd.notna(row_hmdb) else None,
                "website": _normalize_scalar(row["website"]),
            }
            if pd.notna(row_hmdb):
                tags["memorial:website"] = (
                    f"https://www.hmdb.org/m.asp?m={int(row_hmdb)}"
                )
            if "thc:designation" in df.columns and pd.notna(row.get("thc:designation")):
                tags["thc:designation"] = _normalize_scalar(row["thc:designation"])
            if "start_date" in df.columns and pd.notna(row.get("start_date")):
                tags["start_date"] = _normalize_scalar(row["start_date"])
            for col in ("addr:full", "addr:city", "addr:county"):
                if col in df.columns and pd.notna(row.get(col)):
                    tags[col] = _normalize_scalar(row[col])
            for col in (
                "wikimedia_commons",
                "subject:wikimedia_commons",
                "subject:wikipedia",
                "subject:wikidata",
            ):
                if col in df.columns and pd.notna(row.get(col)):
                    tags[col] = _normalize_scalar(row[col])

            nodes.append({"lat": float(lat), "lon": float(lon), "tags": tags})

        except Exception as e:
            row_errors.append(f"row {index}: {e}")

    if row_errors:
        sample = "; ".join(row_errors[:5])
        raise ValueError(f"create_nodes input has invalid rows: {sample}")

    return nodes


def _apply_dedup_check(
    nodes,
    radius_ft,
    name_threshold,
    rate_limit_sec,
    endpoint,
):
    """Filter out nodes that match an existing OSM memorial=plaque nearby.

    Returns ``(kept_nodes, skipped_records)``. ``skipped_records`` is a list
    of dicts pairing each skipped candidate with the matched OSM node for
    manual review.
    """
    kept = []
    skipped = []
    total = len(nodes)
    for i, node in enumerate(nodes, start=1):
        candidate_name = node["tags"].get("name")
        try:
            match = osm_dedup.find_duplicate(
                candidate_lat=node["lat"],
                candidate_lon=node["lon"],
                candidate_name=candidate_name,
                radius_ft=radius_ft,
                name_threshold=name_threshold,
                endpoint=endpoint,
            )
        except Exception as e:
            print(
                f"[WARN] dedup query failed for ref:US-TX:thc="
                f"{node['tags'].get('ref:US-TX:thc')} ({e}); keeping candidate"
            )
            kept.append(node)
        else:
            if match is None:
                kept.append(node)
            else:
                skipped.append(
                    {
                        "candidate": {
                            "name": candidate_name,
                            "lat": node["lat"],
                            "lon": node["lon"],
                            "ref:US-TX:thc": node["tags"].get("ref:US-TX:thc"),
                            "ref:hmdb": node["tags"].get("ref:hmdb"),
                        },
                        "match": match,
                    }
                )
                print(
                    f"[SKIP] {candidate_name!r} ~ OSM node {match['osm_id']} "
                    f"({match['distance_ft']} ft, similarity {match['name_similarity']})"
                )
        if rate_limit_sec and i < total:
            time.sleep(rate_limit_sec)
    return kept, skipped


def push2josm(nodes):
    josm_url = "http://localhost:8111/add_node"
    added_refs = []
    count = 0

    for node in nodes:
        clean_tags = {
            k: v
            for k, v in node["tags"].items()
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
    with open(geojson, "r") as f:
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

    print(f"[OK] Updated {after - before} markers as OSM-present")
    return atlas


def apply_sync_results(atlas, ref_to_osm_id):
    """Stamp ``isOSM=True`` and ``OsmNodeID`` on atlas rows for matched refs.

    ``ref_to_osm_id`` is a ``{str_ref: int_osm_id}`` mapping. Rows whose
    ``ref:US-TX:thc`` is absent from the mapping are left untouched.
    Returns ``(atlas, n_updated, missing_refs)`` where ``missing_refs`` is
    the list of refs from the mapping that did not match any atlas row.
    """
    require_columns(
        atlas, ["ref:US-TX:thc", "isOSM", "OsmNodeID"], context="atlas"
    )
    if not ref_to_osm_id:
        return atlas, 0, []

    # Compare as nullable Int64 so types align with the atlas dtype.
    ref_series = pd.to_numeric(
        atlas["ref:US-TX:thc"], errors="coerce"
    ).astype("Int64")
    mapping_int = {int(k): int(v) for k, v in ref_to_osm_id.items()}

    if not pd.api.types.is_integer_dtype(atlas["OsmNodeID"]):
        atlas["OsmNodeID"] = pd.to_numeric(
            atlas["OsmNodeID"], errors="coerce"
        ).astype("Int64")

    mask = ref_series.isin(mapping_int.keys())
    n_updated = int(mask.sum())
    atlas.loc[mask, "isOSM"] = True
    atlas.loc[mask, "OsmNodeID"] = ref_series[mask].map(mapping_int).astype("Int64")

    found_refs = set(ref_series[mask].dropna().astype(int).tolist())
    missing_refs = sorted(set(mapping_int.keys()) - found_refs)
    return atlas, n_updated, missing_refs


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
    create.add_argument(
        "--only-missing-osm",
        action="store_true",
        help="Only include rows where isHMDB=True and isOSM=False",
    )
    create.add_argument(
        "--dedup-check",
        action="store_true",
        help=(
            "Before emitting each node, query Overpass for nearby memorial=plaque "
            "nodes and skip candidates that fuzzy-match an existing one"
        ),
    )
    create.add_argument(
        "--dedup-distance-ft",
        type=float,
        default=100.0,
        help="Search radius in feet for duplicate detection (default: 100)",
    )
    create.add_argument(
        "--dedup-name-similarity",
        type=float,
        default=0.80,
        help="Minimum normalized name similarity 0..1 to treat as duplicate (default: 0.80)",
    )
    create.add_argument(
        "--dedup-report",
        default="nodes_skipped_for_review.json",
        help="Path for JSON report listing skipped candidates and their matches",
    )
    create.add_argument(
        "--dedup-rate-limit-sec",
        type=float,
        default=1.0,
        help="Seconds to sleep between Overpass queries (default: 1.0)",
    )
    create.add_argument(
        "--overpass-endpoint",
        default=osm_dedup.DEFAULT_OVERPASS_ENDPOINT,
        help="Overpass API endpoint URL",
    )

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

    # sync isOSM + OsmNodeID from live OSM via Overpass
    sync = sub.add_parser(
        "sync-from-osm",
        help=(
            "After a JOSM upload, query Overpass for each ref:US-TX:thc in "
            "nodes.json and stamp isOSM=True + OsmNodeID on matched atlas rows"
        ),
    )
    sync.add_argument("--csv", required=True)
    sync.add_argument("--nodes", required=True)
    sync.add_argument("--out", required=True)
    sync.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Refs per Overpass query (default: 50)",
    )
    sync.add_argument(
        "--rate-limit-sec",
        type=float,
        default=1.5,
        help="Sleep between batched Overpass queries (default: 1.5)",
    )
    sync.add_argument(
        "--overpass-endpoint",
        default=osm_dedup.DEFAULT_OVERPASS_ENDPOINT,
        help="Overpass API endpoint URL",
    )
    sync.add_argument(
        "--report",
        default=None,
        help=(
            "Optional JSON report path listing matched refs, missing refs, "
            "and any ambiguous duplicates"
        ),
    )

    refix = sub.add_parser(
        "refix-osm-ids",
        help=(
            "Batch-push ref:US-TX:thc corrections into JOSM for review "
            "(one load_object call per node, stages a tag change in JOSM)"
        ),
    )
    refix.add_argument("--plan", required=True,
                       help="CSV with columns: id, correct_ref (other cols ignored)")
    refix.add_argument("--state", required=True,
                       help="JSON state file tracking pushed IDs for resumability")
    refix.add_argument("--batch-size", type=int, default=25,
                       help="How many nodes to push in this invocation (default: 25)")
    refix.add_argument("--rate-limit-sec", type=float, default=0.4,
                       help="Sleep between JOSM calls (default: 0.4)")
    refix.add_argument("--josm-endpoint", default=osm_refix.DEFAULT_JOSM_ENDPOINT,
                       help="JOSM Remote Control base URL")
    refix.add_argument("--dry-run", action="store_true",
                       help="Print what would be pushed without contacting JOSM")

    refix_direct = sub.add_parser(
        "refix-osm-direct",
        help=(
            "Push single-tag corrections directly to OSM in batches "
            "(one changeset per batch; bypasses JOSM review)"
        ),
    )
    refix_direct.add_argument("--plan", required=True,
                              help="CSV with columns: id, correct_ref (value to write)")
    refix_direct.add_argument("--state", required=True,
                              help="JSON state file (per-tag-campaign, resumable)")
    refix_direct.add_argument(
        "--tag",
        default="ref:US-TX:thc",
        help="OSM tag key to overwrite on each node (default: ref:US-TX:thc)",
    )
    refix_direct.add_argument("--batch-size", type=int, default=10,
                              help="Nodes per changeset (default: 10)")
    refix_direct.add_argument("--rate-limit-sec", type=float, default=1.0,
                              help="Sleep after each batch (default: 1.0)")
    refix_direct.add_argument(
        "--api-endpoint",
        default=osm_refix_direct.DEFAULT_API_ENDPOINT,
        help="OSM API 0.6 base URL",
    )
    refix_direct.add_argument(
        "--josm-prefs",
        default=None,
        help="Path to JOSM preferences.xml (default: ~/.config/JOSM/preferences.xml)",
    )
    refix_direct.add_argument(
        "--changeset-comment",
        default=None,
        help="Override the default changeset comment",
    )
    refix_direct.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run N batches back-to-back in this invocation (default: 1)",
    )
    refix_direct.add_argument("--dry-run", action="store_true",
                              help="Print what would be pushed without calling OSM")

    args = parser.parse_args()

    # Commands
    if args.cmd == "load":
        atlas = read_atlas(args.file)
        print(atlas.head())
        print(f"[INFO] rows: {len(atlas)}")

    elif args.cmd == "create-nodes":
        df = read_atlas(args.csv)
        if args.only_missing_osm:
            before = len(df)
            df = filter_hmdb_missing_osm(df)
            print(
                f"[INFO] --only-missing-osm: {len(df)} of {before} rows "
                "(isHMDB=True & isOSM=False)"
            )
        nodes = create_nodes(df)

        if args.dedup_check:
            nodes, skipped = _apply_dedup_check(
                nodes,
                radius_ft=args.dedup_distance_ft,
                name_threshold=args.dedup_name_similarity,
                rate_limit_sec=args.dedup_rate_limit_sec,
                endpoint=args.overpass_endpoint,
            )
            with open(args.dedup_report, "w") as f:
                json.dump(skipped, f, indent=2)
            print(
                f"[INFO] Dedup check: kept {len(nodes)}, skipped {len(skipped)} "
                f"→ review {args.dedup_report}"
            )

        with open(args.out, "w") as f:
            json.dump(nodes, f, indent=2)
        print(f"[OK] Generated {len(nodes)} nodes → {args.out}")

    elif args.cmd == "push-josm":
        nodes = json.load(open(args.nodes))
        refs = push2josm(nodes)
        print("[INFO] Returned ref list:", refs)

    elif args.cmd == "find-missing":
        atlas = read_atlas(args.csv)
        missing = find_missing_osm(atlas, args.geo)
        print(missing)

    elif args.cmd == "update-isOSM":
        atlas = read_atlas(args.csv)
        refs = [n["tags"]["ref:US-TX:thc"] for n in json.load(open(args.nodes))]
        updated = update_isOSM(refs, atlas)
        write2csv(updated, args.out)

    elif args.cmd == "sync-from-osm":
        atlas = read_atlas(args.csv)
        with open(args.nodes) as f:
            nodes_payload = json.load(f)
        refs = [n["tags"].get("ref:US-TX:thc") for n in nodes_payload]
        refs = [r for r in refs if r is not None]
        print(f"[INFO] Resolving {len(refs)} refs against OSM via Overpass…")
        ref_to_osm_id = osm_sync.query_osm_nodes_by_thc_refs(
            refs,
            batch_size=args.batch_size,
            endpoint=args.overpass_endpoint,
            rate_limit_sec=args.rate_limit_sec,
        )
        updated, n_updated, missing_refs = apply_sync_results(atlas, ref_to_osm_id)
        resolved_int = {int(k) for k in ref_to_osm_id.keys()}
        unresolved = sorted({int(r) for r in refs} - resolved_int)
        print(
            f"[OK] Matched {len(ref_to_osm_id)} of {len(refs)} refs in OSM; "
            f"stamped {n_updated} atlas rows (isOSM + OsmNodeID)"
        )
        if unresolved:
            print(
                f"[INFO] {len(unresolved)} refs not yet visible in OSM (not uploaded "
                f"or not propagated); leaving atlas rows unchanged"
            )
        write2csv(updated, args.out)
        if args.report:
            report = {
                "matched": ref_to_osm_id,
                "stamped_atlas_rows": n_updated,
                "unresolved_refs": unresolved,
                "refs_not_found_in_atlas": missing_refs,
            }
            with open(args.report, "w") as f:
                json.dump(report, f, indent=2)
            print(f"[OK] Wrote sync report → {args.report}")

    elif args.cmd == "refix-osm-ids":
        plan = osm_refix.load_plan(args.plan)
        osm_refix.run_batch(
            plan,
            state_path=args.state,
            batch_size=args.batch_size,
            rate_limit_sec=args.rate_limit_sec,
            endpoint=args.josm_endpoint,
            dry_run=args.dry_run,
        )

    elif args.cmd == "refix-osm-direct":
        plan = osm_refix.load_plan(args.plan)
        cs_tags = dict(osm_refix_direct.CHANGESET_TAGS)
        if args.changeset_comment:
            cs_tags["comment"] = args.changeset_comment
        total_ok = total_fail = 0
        for i in range(1, max(1, args.repeat) + 1):
            print(f"\n=== batch {i}/{args.repeat} ===")
            out = osm_refix_direct.run_batch_direct(
                plan,
                state_path=args.state,
                batch_size=args.batch_size,
                rate_limit_sec=args.rate_limit_sec,
                endpoint=args.api_endpoint,
                prefs_path=args.josm_prefs,
                changeset_tags=cs_tags,
                tag_name=args.tag,
                dry_run=args.dry_run,
            )
            total_ok += out["ok"]
            total_fail += out["fail"]
            if out["pending_remaining"] == 0:
                print("[OK] no more pending — stopping early")
                break
        print(f"\n[SUMMARY] {total_ok} ok, {total_fail} skipped across "
              f"{i} batch(es)")


if __name__ == "__main__":
    main()

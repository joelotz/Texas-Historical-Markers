# thc/utils.py
import pandas as pd
import json
import requests
from datetime import datetime
import shutil
import subprocess
from rich.console import Console
from rich.table import Table

# -------------- CSV Viewing Utilities -------------- #
# Default PRETTY VIEW (shell formatting)
def viewcsv_pretty(path):
    """Default: Display CSV with column | less formatting."""
    cmd = f"column -s, -t '{path}' | less -S"
    subprocess.run(cmd, shell=True)

# RAW Python print mode
def viewcsv_raw(path, max_rows=200):
    df = pd.read_csv(path)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", shutil.get_terminal_size().columns)
    pd.set_option("display.max_rows", max_rows)
    print(df.to_string(index=False))


# HEAD/TAIL return DataFrame for reuse
def viewcsv_head(path, n):
    return pd.read_csv(path).head(n)

def viewcsv_tail(path, n):
    return pd.read_csv(path).tail(n)

# SEARCH returns filtered dataframe
def viewcsv_search(path, text):
    df = pd.read_csv(path)
    if "name" not in df.columns:
        print("⚠ CSV has no 'name' column")
        return pd.DataFrame()
    mask = df["name"].astype(str).str.contains(text, case=False, na=False)
    return df[mask]

def viewcsv_interactive(df):
    """Scrollable CSV viewer using rich."""
    console = Console()
    table = Table(show_lines=True)

    # Add columns
    for col in df.columns:
        table.add_column(str(col))

    # Add rows
    for _, row in df.iterrows():
        table.add_row(*[str(x) for x in row.values])

    console.print(table)
    console.print("[dim]Press Ctrl+C or q to exit[/dim]")


def convert_hmdb_csv(input_file, output_file):
    """
    Convert HMDB CSV to standardized THC format.

    Fields converted to Int32 (nullable):
        ref:hmdb
        ref:US-TX:thc
    """

    column_map = {
        "MarkerID": "ref:hmdb",
        "Marker No.": "ref:US-TX:thc",
        "Title": "name",
        "Erected By": "ErectedBy",
        "Latitude (minus=S)": "hmdb:Latitude",
        "Longitude (minus=W)": "hmdb:Longitude",
        "Street Address": "addr:full",
        "City or Town": "addr:city",
        "County or Parish": "addr:county",
        "Missing": "isMissing",
    }
    
    df = pd.read_csv(input_file, dtype=str)

    # Verify required columns exist
    missing = [c for c in column_map if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected column(s): {missing}")

    # Select & rename
    df = df[list(column_map.keys())].rename(columns=column_map)

    # Convert reference IDs to integers safely (nullable Int32 like read_atlas)
    for col in ["ref:hmdb", "ref:US-TX:thc"]:
        df[col] = (
            df[col]
            .str.extract(r'(\d+)', expand=False)  # remove non-numeric characters if any
            .fillna("")                      # nullable integer type
        )
    df[col] = df[col].astype("str")

    # Export
    df.to_csv(output_file, index=False)
    print(f"[OK] Converted HMDB → {output_file}")
 #   print(f"[INFO] Numeric integer fields applied to: ref:hmdb, ref:US-TX:thc")
    return df


# -------------- Additional Utility Functions -------------- #
def read_atlas(filename):
    types = {
        'ref:US-TX:thc':'Int32','ref:hmdb':'Int32','start_date':'Int32',
        'UTM Easting':'Int32','UTM Northing':'Int32','UTM Zone':'Int16',
        'isTHC':'boolean','isHMDB':'boolean','isOSM':'boolean',
        'isMissing':'boolean','isPending':'boolean', 'isPrivate':'boolean',
        'Recorded Texas Historic Landmark':'boolean',  'inGoogle':'boolean'
    }
    return pd.read_csv(filename, dtype=types, low_memory=False)


def create_nodes(df):
    nodes = []
    for index, row in df.iterrows():
        try:
            tags = {
                "name": row["name"],
                "historic": "memorial",
                "memorial": "plaque",
                "material": "aluminium",
                "support": "pole",
                "operator": "Texas Historical Commission",
                "operator:wikidata": "Q2397965",
                "thc:designation": "Historical Marker",
                "start_date": row["start_date"],
                "ref:US-TX:thc": row["ref:US-TX:thc"],
                "ref:hmdb": row["ref:hmdb"],
                "source:website": row["website"],
                "memorial:website": f"https://www.hmdb.org/m.asp?m={row['ref:hmdb']}"
            }

            nodes.append({
                "lat": row["hmdb:Latitude"],
                "lon": row["hmdb:Longitude"],
                "tags": tags
            })

        except Exception as e:
            print(f"[WARN] Failed row {index}: {e}")

    return nodes


def push2josm(nodes):
    url = "http://localhost:8111/add_node"
    added = []
    for n in nodes:
        tag_str = "|".join(f"{k}={v}" for k,v in n["tags"].items())
        r = requests.get(url, params={"lat":n["lat"],"lon":n["lon"],"addtags":tag_str})
        if r.status_code == 200:
            added.append(n["tags"]["ref:US-TX:thc"])
        else:
            print(f"[FAIL] {r.status_code} @ {n['lat']},{n['lon']}")
    print(f"[OK] {len(added)} nodes pushed")
    return added


def write2csv(df, filename, date=False):
    if date:
        filename=f"./file_backup/{datetime.now():%Y%m%d}_{filename}"
    df.to_csv(filename,index=False)
    print(f"[OK] wrote {filename}")


def find_missing_osm(atlas, geojson):
    with open(geojson) as f: data = json.load(f)
    osm_refs = {
        int(f["properties"]["ref:US-TX:thc"])
        for f in data.get("features",[])
        if "ref:US-TX:thc" in f.get("properties",{})
    }
    atlas_refs = set(atlas["ref:US-TX:thc"].dropna().astype(int))
    missing = sorted(atlas_refs - osm_refs)
    print(f"[INFO] missing: {len(missing)}")
    return missing


def update_isOSM(refs, atlas):
    before = atlas["isOSM"].sum()
    atlas.loc[atlas["ref:US-TX:thc"].isin(refs),"isOSM"]=True
    print(f"[OK] updated {atlas['isOSM'].sum()-before} flags")
    return atlas

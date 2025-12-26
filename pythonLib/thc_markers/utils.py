# thc/utils.py
import pandas as pd
import json
import requests
from datetime import datetime


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

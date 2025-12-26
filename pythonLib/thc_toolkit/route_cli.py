#!/usr/bin/env python3
"""
THC Route Proximity Mapper CLI
------------------------------

Maps THC markers located within range of a KML route.

Examples:
    routes --track trip.kml --data data.csv
    routes --track trip.kml --data data.csv --unmapped --openmap
    routes --track trip.kml --data data.csv --radius 10 --csv

Outputs:
    near_route_map_<tag>_<radius>mi.html
    near_route_<tag>_<radius>mi.csv
    THC_markers_route_<tag>_<radius>mi.kml
    combined_route_markers_<tag>_<radius>mi.geojson
"""

import argparse
import pandas as pd
import pyproj, html, webbrowser, geopandas as gpd, folium
from folium.plugins import MarkerCluster
from folium import LayerControl
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import transform
import xml.etree.ElementTree as ET


# ----------------------------------------------------------
# Load route KML → LineString or MultiLineString
# ----------------------------------------------------------
def load_kml_route(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    segments = []
    for c in root.findall(".//kml:coordinates", ns):
        if not c.text:
            continue
        coords = []
        for row in c.text.strip().split():
            lon, lat = map(float, row.split(",")[:2])
            coords.append((lon, lat))
        if len(coords) >= 2:
            segments.append(LineString(coords))

    if not segments:
        raise ValueError("❌ No route coordinates found in KML")

    return segments[0] if len(segments) == 1 else MultiLineString(segments)


# ----------------------------------------------------------
# Main Processing
# ----------------------------------------------------------
def run_with_args(track, data, radius=5, unmapped=False,
                  only_mapped=False, csv=False, csv_simple=False, 
                  geojson=False, kml=False, openmap=False):

    tag = "unmapped" if unmapped else "all"

    print(f"\n📍 Loading route → {track}")
    route = load_kml_route(track)

    print(f"📄 Loading dataset → {data}")
    df = pd.read_csv(data, low_memory=False)

    # ---------- Filter Markers ----------
    hmdb = df["ref:hmdb"].astype(str).str.strip().str.lower()
    is_unmapped = hmdb.isin(["", "nan", "none"])
    is_mapped   = ~is_unmapped

    if unmapped and only_mapped:
        raise ValueError("Choose only one filter: --unmapped OR --only_mapped")

    if unmapped:
        markers = df[is_unmapped].copy()
        tag = "unmapped"
    elif only_mapped:
        markers = df[is_mapped].copy()
        tag = "mapped"
    else:
        markers = df.copy()
        tag = "all"


    # ---------- Spatial Filtering ----------
    LAT, LON = "thc:Latitude", "thc:Longitude"
    markers[LAT] = pd.to_numeric(markers[LAT], errors="coerce")
    markers[LON] = pd.to_numeric(markers[LON], errors="coerce")
    markers = markers.dropna(subset=[LAT, LON]).copy()
    markers["geometry"] = markers.apply(lambda r: Point(r[LON], r[LAT]), axis=1)

    proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    rp = transform(proj, route)

    near = markers[
        markers["geometry"].apply(lambda p: rp.distance(transform(proj,p))/1609.34 <= radius)
    ].copy(deep=True)     # 👈 REQUIRED to kill SettingWithCopyWarning

    print(f"✓ {len(near)} markers found within {radius} miles ({tag})\n")

    # ----------------------------------------------------------
    # Map Generation
    # ----------------------------------------------------------
    if isinstance(route, LineString):
        segs = [list(route.coords)]
    else:
        segs = [list(g.coords) for g in route.geoms]

    allpts = [pt for seg in segs for pt in seg]
    center_lon, center_lat = allpts[len(allpts)//2]

    m = folium.Map(location=[center_lat, center_lon], zoom_start=9)

    # Draw route
    for seg in segs:
        folium.PolyLine([(lat, lon) for lon, lat in seg], color="blue", weight=4).add_to(m)

    # Marker layers
    unmapped_layer = MarkerCluster(name="Unmapped")
    mapped_layer   = MarkerCluster(name="Mapped")

    for _, r in near.iterrows():
        hmdb = str(r.get("ref:hmdb", "")).strip().lower()
        unm = hmdb in ["", "nan", "none"]
        color = "#E74C3C" if unm else "#2ECC71"       # red unmapped, green mapped
        size  = 6 if unm else 4

        popup = (
            f"<b>{html.escape(str(r.get('name','Unknown')))}</b><br>"
            f"County: {r.get('addr:county','')}<br>"
            f"HMDB: {r.get('ref:hmdb','')}"
        )

        folium.CircleMarker(
            [r[LAT], r[LON]],
            radius=size, color=color, fill=True, popup=popup,
            tooltip=r.get("name","Marker")
        ).add_to(unmapped_layer if unm else mapped_layer)

    unmapped_layer.add_to(m)
    mapped_layer.add_to(m)
    LayerControl().add_to(m)

    # --- Enforce output column formats (integer-safe & warning-free) ----------
    int_fields = ["ref:US-TX:thc", "ref:hmdb", "OsmNodeID"]

    for col in int_fields:
        if col in near.columns:
            near[col] = (
                pd.to_numeric(near[col], errors="coerce")   # numbers or <NA>
                .astype("Int64")                          # final type — NO WARNINGS 🎉
            )


    # Save/Export
    html_file = f"near_route_map_{tag}_{radius}mi.html"
    m.save(html_file)
    print(f"🗺 Map saved → {html_file}")
    if openmap:
        webbrowser.open(html_file)

    if csv:
        csv_file = f"near_route_{tag}_{radius}mi.csv"
        near.to_csv(csv_file, index=False)
        print(f"📝 CSV saved → {csv_file}")

    # ---------- Simple CSV Export ----------
    if csv_simple:
        simple_fields = [
            "ref:US-TX:thc", "ref:hmdb", "OsmNodeID", "name", 
            "website", "memorial:website", "addr:city", "addr:county",
            "thc:Latitude", "thc:Longitude"
        ]

        # Keep columns that exist in data (so it won't crash)
        cols = [c for c in simple_fields if c in near.columns]

        csv_file_simple = f"near_route_{tag}_{radius}mi_simple.csv"
        near[cols].to_csv(csv_file_simple, index=False)
        print(f"📄 Simple CSV saved → {csv_file_simple}")


    if geojson:
        gdf = gpd.GeoDataFrame(near.copy(), geometry="geometry", crs="EPSG:4326")
        route_gdf = gpd.GeoDataFrame([{"name":"route","geometry":route}], crs="EPSG:4326")
        j_file = f"combined_route_markers_{tag}_{radius}mi.geojson"
        pd.concat([route_gdf, gdf]).to_file(j_file, driver="GeoJSON")
        print(f"🌍 GeoJSON saved → {j_file}")

    if kml:
        kml_file = f"THC_markers_route_{tag}_{radius}mi.kml"
        with open(kml_file,"w") as f:
            f.write('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>')
            for _,r in near.iterrows():
                f.write(f"<Placemark><name>{html.escape(str(r.get('name')))}</name>"
                        f"<Point><coordinates>{r[LON]},{r[LAT]},0</coordinates></Point></Placemark>")
            f.write("</Document></kml>")
        print(f"📌 KML saved → {kml_file}")


# ----------------------------------------------------------
# CLI
# ----------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Find THC markers located near a KML route.")

    p.add_argument("--track", required=True, help="Input KML file")
    p.add_argument("--data", required=True, help="CSV dataset of markers")
    p.add_argument("--radius", type=float, default=5, help="Search distance in miles")

    # ---- Filtering flags (mutually exclusive) ----
    group = p.add_mutually_exclusive_group()
    group.add_argument("--unmapped", action="store_true", help="Show only unmapped markers")
    group.add_argument("--only_mapped", action="store_true", help="Show only mapped markers")

    # ---- Output format options ----
    p.add_argument("--openmap", action="store_true", help="Open map automatically")
    p.add_argument("--csv", action="store_true", help="Export results to CSV")
    p.add_argument("--csv_simple", action="store_true", help="Export a simplified CSV with core fields only")
    p.add_argument("--geojson", action="store_true", help="Export GeoJSON")
    p.add_argument("--kml", action="store_true", help="Export KML")

    args = p.parse_args()
    run_with_args(**vars(args))

if __name__ == "__main__":
    main()
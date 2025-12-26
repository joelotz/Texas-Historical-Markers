#!/usr/bin/env python3
"""
THC Route Proximity Mapper CLI
------------------------------

Maps THC markers located within range of a KML route.

Usage Examples:
    python route_cli.py --track trip.kml --data data.csv
    python route_cli.py --track track.kml --data data.csv --unmapped --open
    python route_cli.py --track road.kml --data data.csv --radius 10 --export-csv

Outputs:
    near_route_map_<tag>_<radius>mi.html
    near_route_<tag>_<radius>mi.csv
    THC_markers_route_<tag>_<radius>mi.kml
    combined_route_markers_<tag>.geojson
"""

import argparse
import pandas as pd
import pyproj, html, webbrowser, geopandas as gpd, folium
from folium.plugins import MarkerCluster
from folium import LayerControl, FeatureGroup, GeoJson
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import transform
import xml.etree.ElementTree as ET


# ---------------- Load Route File ---------------- #
def load_kml_route(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    segments = []

    # Each <coordinates> block becomes its own LineString segment
    for c in root.findall(".//kml:coordinates", ns):
        if c.text is None:
            continue

        coords = []
        for row in c.text.strip().split():
            parts = row.split(",")
            if len(parts) < 2:
                continue
            lon, lat = map(float, parts[:2])
            coords.append((lon, lat))

        if len(coords) >= 2:
            segments.append(LineString(coords))

    if not segments:
        raise ValueError("No route coordinates found in KML")

    # If only one segment, just return a LineString; otherwise MultiLineString
    if len(segments) == 1:
        return segments[0]
    else:
        return MultiLineString(segments)


# ---------------- Core Logic ---------------- #
def run_with_args(track_file, data_file, radius=5, unmapped=False,
                  include_all=False, export_csv=False, geojson=False,
                  kml=False, open_map=False):

    only_unmapped = unmapped and not include_all
    tag="unmapped" if only_unmapped else "all"

    print(f"Loading route → {track_file}")
    route=load_kml_route(track_file)

    print(f"Loading dataset → {data_file}")
    df=pd.read_csv(data_file, low_memory=False)

# ---------------- Filtering ---------------- #
    if only_unmapped:
        # Normalize HMDB column for comparison
        hmdb = df["ref:hmdb"].astype(str).str.strip().str.lower().replace("nan","")

        # Select unmapped markers → make explicit copy to avoid SettingWithCopyWarning
        markers = df[
            hmdb.isna() |
            (hmdb == "") |
            (hmdb == "nan") |
            (hmdb == "none")
        ].copy()

    else:
        # No filtering → full dataset but still use a clean copy
        markers = df.copy()

    LAT="thc:Latitude"; LON="thc:Longitude"
    markers[LAT]=pd.to_numeric(markers[LAT],errors="coerce")
    markers[LON]=pd.to_numeric(markers[LON],errors="coerce")
    markers=markers.dropna(subset=[LAT,LON]).copy()
    markers["geometry"]=markers.apply(lambda r:Point(r[LON],r[LAT]),axis=1)

    proj=pyproj.Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True).transform
    rp=transform(proj,route)

    near=markers[markers["geometry"].apply(lambda p:rp.distance(transform(proj,p))/1609.34<=radius)]
    print(f"✓ Found {len(near)} {tag} markers within {radius} miles of route")

    # ---------------- Map ---------------- #

    # Build a list of segments and a flat list of all coords for centering
    if isinstance(route, LineString):
        segments = [list(route.coords)]
    else:  # MultiLineString
        segments = [list(geom.coords) for geom in route.geoms]

    all_coords = [pt for seg in segments for pt in seg]
    mid = len(all_coords) // 2
    center_lon, center_lat = all_coords[mid]

    m = folium.Map(location=[center_lat, center_lon], zoom_start=9)

    # Draw each segment separately (no artificial “closing” between them)
    for seg in segments:
        route_coords = [(lat, lon) for lon, lat in seg]  # flip for folium
        folium.PolyLine(route_coords, color="blue", weight=4).add_to(m)

    cU=MarkerCluster(name="Unmapped"); cM=MarkerCluster(name="Mapped")
    for _,r in near.iterrows():
        hmdb = str(r.get("ref:hmdb","")).strip().lower()
        unmapped_marker = (hmdb == "" or hmdb == "nan" or hmdb == "none")
        mapped = not unmapped_marker  # True = mapped | False = unmapped
        col = "#2ECC71" if mapped else "#E74C3C"  # nicer green/red
        radius = 16 if unmapped_marker else 4  # larger if unmapped
         
        pop=f"<b>{r.get('name','Unknown')}</b><br>County:{r.get('addr:county','')}<br>HMDB:{r.get('ref:hmdb','')}"
        folium.CircleMarker([r[LAT],r[LON]],radius=5,color=col,fill=True,
                            popup=pop,tooltip=r.get("name","Marker")
        ).add_to(cM if mapped else cU)

    cU.add_to(m); cM.add_to(m); LayerControl().add_to(m)

    html_name=f"near_route_map_{tag}_{radius}mi.html"
    m.save(html_name); print("📍 Map saved:",html_name)
    if open_map: webbrowser.open(html_name)

    if export_csv:
        csv_name=f"near_route_{tag}_{radius}mi.csv"
        near.to_csv(csv_name,index=False); print("📝 CSV:",csv_name)

    if geojson:
        gdf=gpd.GeoDataFrame(near.copy(),geometry="geometry",crs="EPSG:4326")
        route_gdf=gpd.GeoDataFrame([{"name":"route","geometry":route}],crs="EPSG:4326")
        out=pd.concat([route_gdf,gdf],ignore_index=True)
        j=f"combined_route_markers_{tag}_{radius}mi.geojson"
        out.to_file(j,driver="GeoJSON"); print("🌍 GeoJSON:",j)

    if kml:
        def esc(t):return""if t is None else html.escape(str(t))
        fn=f"THC_markers_route_{tag}_{radius}mi.kml"
        with open(fn,"w")as f:
            f.write('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>')
            for _,r in near.iterrows():
                f.write(f"<Placemark><name>{esc(r.get('name'))}</name>"
                        f"<Point><coordinates>{r[LON]},{r[LAT]},0</coordinates></Point></Placemark>")
            f.write("</Document></kml>")
        print("🗺 KML:",fn)


# ---------------- CLI Entry ---------------- #
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--track",required=True)
    p.add_argument("--data",required=True)
    p.add_argument("--radius",type=float,default=5)
    p.add_argument("--unmapped",action="store_true")
    p.add_argument("--all",action="store_true")
    p.add_argument("--export-csv",action="store_true")
    p.add_argument("--geojson",action="store_true")
    p.add_argument("--kml",action="store_true")
    p.add_argument("--open",action="store_true")
    args=p.parse_args()
    run_with_args(**vars(args))


if __name__ == "__main__":
    main()

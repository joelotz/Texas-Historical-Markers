#!/usr/bin/env python3
#!/usr/bin/env python3
"""
Texas Historical Markers – Route Mapper CLI
-------------------------------------------

This tool analyzes a KML route (road trip, track, path, etc.) and identifies 
Texas Historical Markers located within a user-defined search radius from the 
route polyline. Markers may be displayed on an interactive map, exported to CSV,
saved as GeoJSON/KML, or opened directly in your browser.

--------------------------------------------------------------
Core Functionality
--------------------------------------------------------------
• Load a KML route and THC marker dataset (CSV)
• Compute proximity to the route using geodesic distance
• Optionally filter to *unmapped markers only* (missing HMDB ref)
• Generate a Folium web map with:
      🟥 unmapped markers (no HMDB ID)
      🟩 mapped markers (ref:hmdb present)
• Export results (CSV, GeoJSON, KML)
• Optional automatic browser launch

--------------------------------------------------------------
Inputs Required
--------------------------------------------------------------
--track <file.kml>     KML track/route file containing coordinates
--data  <data.csv>     Texas Historical Markers dataset

CSV must include:
    thc:Latitude, thc:Longitude
    ref:hmdb (optional if running --all)

--------------------------------------------------------------
Optional Parameters
--------------------------------------------------------------
--radius <miles>       Search distance from route (default: 5 miles)
--unmapped             Include *only unmapped markers*
--all                  Include both mapped + unmapped (overrides --unmapped)

Export Options:
--export-csv           Save nearby markers to CSV
--geojson              Export combined route + markers as GeoJSON
--kml                  Create Google Earth compatible KML

Map Behavior:
--open                 Auto-open interactive map page after generation

--------------------------------------------------------------
Example Use Cases
--------------------------------------------------------------
Basic run:
    python MarkersAlongTrack.py --track track01.kml --data data.csv

Unmapped markers only within 5 miles (default radius):
    python MarkersAlongTrack.py --track route.kml --data data.csv --unmapped

Larger radius + export dataset:
    python MarkersAlongTrack.py --track trip.kml --data data.csv --radius 10 --export-csv

GIS export formats:
    python MarkersAlongTrack.py --track trip.kml --data data.csv --geojson --kml

Auto-open map after build:
    python MarkersAlongTrack.py --track my.kml --data markers.csv --open

--------------------------------------------------------------
Output Files Generated
--------------------------------------------------------------
near_route_map_<tag>_<radius>mi.html    Interactive Folium map
near_route_<tag>_<radius>mi.csv         CSV export (if --export-csv used)
THC_markers_route_<tag>_<radius>mi.kml  KML export (if --kml used)
combined_route_markers_<tag>.geojson    GeoJSON (if --geojson used)

Where <tag> is either:
    "unmapped" — only missing HMDB references
    "all"      — mapped + unmapped

--------------------------------------------------------------
Notes
--------------------------------------------------------------
• Route midpoint determines initial map center.
• Distance calculations use projected CRS for speed.
• Latitude/Longitude must be valid numeric values.
• KML export does not currently include style/icons (expandable later).

--------------------------------------------------------------
Future Enhancements (good candidates)
--------------------------------------------------------------
• Multi-route comparison & batch processing
• Output GPX for navigation apps (Garmin/OSMand)
• Auto-download StreetView preview links
• Click-to-open HMDB page when mapped
• Waypoint navigation integration for fieldwork
"""


import argparse
import os
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import transform
from geopy.distance import geodesic
import pyproj
import folium
from folium.plugins import MarkerCluster
from folium import LayerControl, FeatureGroup, GeoJson
import geopandas as gpd
import webbrowser
import html


# ---------------------------------------------------------------
# Load Route from KML
# ---------------------------------------------------------------
import xml.etree.ElementTree as ET

def load_kml_route(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    coords = []
    for c in root.findall(".//kml:coordinates", ns):
        text = c.text.strip()
        for row in text.split():
            lon, lat, *_ = map(float, row.split(","))
            coords.append((lon, lat))

    return LineString(coords)


# ---------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------
def get_args():
    p = argparse.ArgumentParser(description="Texas Historical Marker Route Mapper")

    p.add_argument("--track", required=True, help="Input KML route file")
    p.add_argument("--data", required=True, help="Input Texas Historical Marker CSV")
    p.add_argument("--radius", type=float, default=5, help="Search radius (miles)")
    p.add_argument("--unmapped", action="store_true", help="Filter to unmapped markers only")
    p.add_argument("--all", action="store_true", help="Include both mapped & unmapped markers")
    p.add_argument("--export-csv", action="store_true", help="Export marker results to CSV")
    p.add_argument("--geojson", action="store_true", help="Export combined GeoJSON")
    p.add_argument("--kml", action="store_true", help="Export clean Google-compatible KML")
    p.add_argument("--open", action="store_true", help="Open map in browser after export")

    return p.parse_args()


# ---------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------
def main():
    args = get_args()

    track_file = args.track
    data_file = args.data
    radius = args.radius
    only_unmapped = args.unmapped and not args.all
    tag = "unmapped" if only_unmapped else "all"

    # Load route
    print(f"Loading route from {track_file} ...")
    route = load_kml_route(track_file)

    # Load CSV
    print(f"Loading marker dataset from {data_file} ...")
    df = pd.read_csv(data_file, low_memory=False)

    # Filter mapped/unmapped
    if only_unmapped:
        markers = df[df["ref:hmdb"].isna() | (df["ref:hmdb"].astype(str).str.strip() == "")]
    else:
        markers = df.copy()

    LAT_COL = "thc:Latitude"
    LON_COL = "thc:Longitude"

    # Clean coords
    markers[LAT_COL] = pd.to_numeric(markers[LAT_COL], errors='coerce')
    markers[LON_COL] = pd.to_numeric(markers[LON_COL], errors='coerce')
    markers = markers.dropna(subset=[LAT_COL, LON_COL]).copy()

    markers["geometry"] = markers.apply(lambda r: Point(r[LON_COL], r[LAT_COL]), axis=1)

    # Distance projection
    proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    route_proj = transform(proj, route)

    def fast_distance_miles(pt):
        return route_proj.distance(transform(proj, pt)) / 1609.34

    near = markers[markers["geometry"].apply(lambda p: fast_distance_miles(p) <= radius)]

    print(f"✓ Found {len(near)} {tag} markers within {radius} miles of route")

    # -------------------------------------------------------
    # Build Folium Map
    # -------------------------------------------------------
    mid = len(route.coords) // 2
    c_lon, c_lat = route.coords[mid]
    m = folium.Map(location=[c_lat, c_lon], zoom_start=9)

    fg_route = FeatureGroup(name="Route Line", show=True)

    GeoJson(route).add_to(fg_route)

    clu_unmapped = MarkerCluster(name="Unmapped Markers")
    clu_mapped = MarkerCluster(name="Mapped Markers")

    for _, row in near.iterrows():
        lat, lon = row[LAT_COL], row[LON_COL]
        name = row.get("name", "Unnamed Marker")
        val = row.get("ref:hmdb")
        mapped = pd.notna(val) and str(val).strip() != ""

        color = "green" if mapped else "red"
        popup_html = f"<b>{name}</b><br>County: {row.get('addr:county','')}<br>HMDB: {val if mapped else '<i>None</i>'}"

        marker = folium.CircleMarker(location=[lat, lon], radius=5, color=color,
                                    fill=True, fill_opacity=0.85,
                                    popup=popup_html, tooltip=name)

        (clu_mapped if mapped else clu_unmapped).add_to(m)  # attach cluster
        marker.add_to(clu_mapped if mapped else clu_unmapped)

    fg_route.add_to(m)
    clu_unmapped.add_to(m)
    clu_mapped.add_to(m)
    LayerControl(collapsed=False).add_to(m)

    outfile = f"near_route_map_{tag}_{radius}mi.html"
    m.save(outfile)
    print(f"📍 Map saved → {outfile}")

    if args.open:
        webbrowser.open(outfile)


    # -------------------------------------------------------
    # CSV export
    # -------------------------------------------------------
    if args.export_csv:
        csv_out = f"near_route_{tag}_{radius}mi.csv"
        near.to_csv(csv_out, index=False)
        print(f"📝 CSV saved → {csv_out}")


    # -------------------------------------------------------
    # GeoJSON export
    # -------------------------------------------------------
    if args.geojson:
        gdf = gpd.GeoDataFrame(near.copy(), geometry="geometry", crs="EPSG:4326")
        route_gdf = gpd.GeoDataFrame([{"name":"route","geometry":route}], crs="EPSG:4326")
        output = pd.concat([route_gdf, gdf], ignore_index=True)
        out = f"combined_route_markers_{tag}_{radius}mi.geojson"
        output.to_file(out, driver="GeoJSON")
        print(f"🌍 GeoJSON saved → {out}")


    # -------------------------------------------------------
    # KML Export
    # -------------------------------------------------------
    if args.kml:
        def xml_safe(text): return "" if text is None else html.escape(str(text))
        kml_name = f"THC_markers_route_{tag}_{radius}mi.kml"

        with open(kml_name, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
""")

            for _, r in near.iterrows():
                lat, lon = r[LAT_COL], r[LON_COL]
                name = xml_safe(r.get("name","Unknown"))
                hmdb = xml_safe(r.get("ref:hmdb",""))
                status = "mapped" if hmdb else "unmapped"

                f.write(f"""
<Placemark>
    <name>{name}</name>
    <description>HMDB: {hmdb}</description>
    <Point><coordinates>{lon},{lat},0</coordinates></Point>
</Placemark>
""")

            f.write("""</Document></kml>""")

        print(f"🗺 KML saved → {kml_name}")


if __name__ == "__main__":
    main()

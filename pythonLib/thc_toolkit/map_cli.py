"""
THC County/City Marker Mapper CLI
---------------------------------

Maps THC markers by county and optional city filters.

Examples:
    thc map --data data.csv --county Grayson
    thc map --data data.csv --county Grayson --city Sherman --unmapped --openmap
    thc map --data data.csv --county Grayson --csv --geojson --kml

Outputs:
    marker_map_<tag>.html
    markers_<tag>.csv
    markers_<tag>_simple.csv
    markers_<tag>.geojson
    markers_<tag>.kml
"""

import argparse
import os
import webbrowser
import pandas as pd
import folium

from .utils import read_atlas


def require_columns(df, required_columns, context="dataframe"):
    """Raise a clear error when required columns are missing."""
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{context} missing required column(s): {', '.join(missing)}"
        )


def filter_markers(df, county=None, city=None, unmapped=False):
    required = ["isMissing", "hmdb:Latitude", "hmdb:Longitude", "thc:Latitude", "thc:Longitude"]
    if county:
        required.append("addr:county")
    if city:
        required.append("addr:city")
    if unmapped:
        required.append("isOSM")
    require_columns(df, required, context="map input")

    mask = ~df["isMissing"]

    if county:
        mask &= df["addr:county"].astype(str).str.strip().str.lower().eq(county.strip().lower())

    if city:
        mask &= df["addr:city"].astype(str).str.strip().str.lower().eq(city.strip().lower())

    if unmapped:
        mask &= ~df["isOSM"]

    out = df.loc[mask].copy()

    out["map_lat"] = out["hmdb:Latitude"].fillna(out["thc:Latitude"])
    out["map_lon"] = out["hmdb:Longitude"].fillna(out["thc:Longitude"])

    out = out[out["map_lat"].notna() & out["map_lon"].notna()].copy()
    return out


def build_tag(county=None, city=None, unmapped=False):
    parts = []
    if county:
        parts.append(county.replace(" ", "_"))
    if city:
        parts.append(city.replace(" ", "_"))
    if unmapped:
        parts.append("unmapped")
    return "_".join(parts) if parts else "all"


def write_html_map(df, outfile, title=None):
    if df.empty:
        print("No markers found to map.")
        return

    center_lat = df["map_lat"].mean()
    center_lon = df["map_lon"].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

    for _, row in df.iterrows():
        popup = folium.Popup(
            f"""
            <b>{row.get('name', '')}</b><br>
            THC: {row.get('ref:US-TX:thc', '')}<br>
            HMDB: {row.get('ref:hmdb', '')}<br>
            City: {row.get('addr:city', '')}<br>
            County: {row.get('addr:county', '')}<br>
            isOSM: {row.get('isOSM', '')}
            """,
            max_width=300,
        )

        folium.Marker(
            location=[row["map_lat"], row["map_lon"]],
            popup=popup,
            tooltip=str(row.get("name", "")),
        ).add_to(m)

    m.save(outfile)
    print(f"Wrote {outfile}")


def run_with_args(args):
    df = read_atlas(args.data)

    filtered = filter_markers(
        df,
        county=args.county,
        city=args.city,
        unmapped=args.unmapped,
    )

    tag = build_tag(args.county, args.city, args.unmapped)

    html_file = f"marker_map_{tag}.html"
    write_html_map(filtered, html_file)

    if args.csv:
        csv_file = f"markers_{tag}.csv"
        filtered.to_csv(csv_file, index=False)
        print(f"Wrote {csv_file}")

    if args.simple:
        simple_cols = [
            "ref:US-TX:thc",
            "ref:hmdb",
            "name",
            "addr:city",
            "addr:county",
            "map_lat",
            "map_lon",
            "isOSM",
        ]
        require_columns(filtered, simple_cols, context="map simple export")
        simple_file = f"markers_{tag}_simple.csv"
        filtered[simple_cols].to_csv(simple_file, index=False)
        print(f"Wrote {simple_file}")

    if args.geojson:
        geojson_file = f"markers_{tag}.geojson"
        features = []
        for _, row in filtered.iterrows():
            props = row.drop(labels=["map_lat", "map_lon"]).to_dict()
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["map_lon"], row["map_lat"]],
                },
                "properties": props,
            })

        geojson = {"type": "FeatureCollection", "features": features}
        import json
        with open(geojson_file, "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2, default=str)
        print(f"Wrote {geojson_file}")

    if args.kml:
        kml_file = f"markers_{tag}.kml"
        with open(kml_file, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n')
            for _, row in filtered.iterrows():
                name = str(row.get("name", "")).replace("&", "&amp;")
                f.write("  <Placemark>\n")
                f.write(f"    <name>{name}</name>\n")
                f.write("    <Point>\n")
                f.write(f"      <coordinates>{row['map_lon']},{row['map_lat']},0</coordinates>\n")
                f.write("    </Point>\n")
                f.write("  </Placemark>\n")
            f.write("</Document>\n</kml>\n")
        print(f"Wrote {kml_file}")

    if args.openmap:
        webbrowser.open(f"file://{os.path.abspath(html_file)}")


def main():
    parser = argparse.ArgumentParser(
        description="Map THC markers by county/city."
    )
    parser.add_argument("--data", required=True)
    parser.add_argument("--county")
    parser.add_argument("--city")
    parser.add_argument("--unmapped", action="store_true")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--simple", action="store_true")
    parser.add_argument("--geojson", action="store_true")
    parser.add_argument("--kml", action="store_true")
    parser.add_argument("--openmap", action="store_true")

    args = parser.parse_args()
    run_with_args(args)


if __name__ == "__main__":
    main()

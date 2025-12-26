## 🗺️ Texas Historical Markers Toolkit

Processing • Mapping • Route Planning • Data Export

This package provides tools for working with **Texas Historical Marker datasets**, including:

*   Exporting **unmapped markers per county**
*   Generating **maps of markers near a KML route**
*   Exporting **CSV, GeoJSON, and KML**
*   CLI or Python-library style usage

Perfect for field research, HMDB contribution, road trip planning, and dataset curation.

## 📦 Installation

Clone or place the project folder locally, then install in **editable mode**:

```sh
cd pythonLib
pip install -e .
```

This makes the CLI available system-wide and allows editing the code without re-installation.

## 📁 Project Structure

```sh
pythonLib/
├─ pyproject.toml
├─ README.md
└─ thc_markers/
   ├─ counties_cli.py
   ├─ route_cli.py
   ├─ cli.py              ← unified command entrypoint
   ├─ utils.py
   └─ __init__.py
```

## 🚀 Usage

Run from any directory after installation:

### 1\. County Export & Filtering

```sh
thc counties --input data.csv --output UnmappedMarkersPerCounty
```

Exports one CSV per county containing unmapped, non-private, non-missing markers.

Options:

```sh
thc counties --county Denton                               # only Denton county
thc counties --stats                                                 # print summary table
thc counties --merge all.csv                                # create one combined CSV
thc counties --summary-json summary.json     # export counts to JSON
```

Default assumptions if no args provided:

| Parameter | Default |
| --- | --- |
| Input CSV | `data.csv` |
| Output directory | `UnmappedMarkersPerCounty/` |

### 2\. Route-Based Marker Mapping

Generate interactive Folium maps + exports:

```sh
thc route --track track.kml --data data.csv
```

Filter to unmapped only:

```sh
thc route --track trip.kml --data data.csv --unmapped
```

Common export options:

```sh
thc route --track trip.kml --data data.csv --export-csv
thc route --track trip.kml --data data.csv --geojson --kml
thc route --track trip.kml --data data.csv --open     # auto-launch map
```

Generated files:

| Output | Created When |
| --- | --- |
| near\_route\_map\_<tag>\_<radius>mi.html | Always |
| near\_route\_<tag>\_<radius>mi.csv | \--export-csv |
| combined\_route\_markers\_<tag>.geojson | \--geojson |
| THC\_markers\_route\_<tag>\_<radius>mi.kml | \--kml |

## 🔥 Import as a Python Library

```sh
from thc_markers.counties_cli import load_filtered, export_counties
from thc_markers.route_cli import run_with_args

df = load_filtered("data.csv")
export_counties(df, "results")

run_with_args(track_file="track.kml", data_file="data.csv", unmapped=True)
```

No CLI parsing required.
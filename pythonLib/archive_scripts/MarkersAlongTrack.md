# 📍 Texas Historical Marker Mapping Tool

Map Texas Historical Commission markers along a GPS route, identify locations missing HMDB entries, and generate export-ready files for field trips, MyMaps, QGIS, or offline mapping.

This project loads a KML route (`track01.kml`) and a THC marker dataset (`data.csv`), filters markers within a chosen radius, and generates an interactive Folium map with visual highlighting of mapped vs unmapped markers.

---

## 🚀 Features

- Load and parse **KML GPS track** as LineString  
- Read **Texas Historical Marker dataset (CSV)**  
- Automatically filter:
  - All markers  
  - or only **unmapped (no HMDB reference)**  
- Distance-based selection — markers **within N miles of route**
- Auto-generated **interactive Folium map**
- Color-coded markers:
  - 🔴 Unmapped (no HMDB ref)
  - 🟢 Mapped
  - 🔷 Route polyline
- Export options
  - `*.html` (Folium interactive map)
  - `*.kml` (Google MyMaps / Google Earth)
  - `*.geojson` (QGIS, geojson.io)
  - `*.csv` (filtered marker list)
- Optional Jupyter widgets to export **Unmapped/All KML** on demand

---

## 🛠 Installation & Setup

### Create and activate virtual environment

```bash
mkdir -p ~/venvs
python3 -m venv ~/venvs/markers
source ~/venvs/markers/bin/activate
pip install --upgrade pip

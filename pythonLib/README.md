
# 🗺️ Texas Historical Markers Toolkit

Processing • Mapping • OSM Sync • Route Planning • Data Export  
A Python + CLI toolkit for working with **Texas Historical Marker (THC) datasets**, including:


* Exporting **unmapped markers per county**
* Route-based marker visualization with **Folium interactive maps**
* Conversion to **OSM/JOSM nodes** for mapping work
* CSV ↔ SQLite sync for faster filtering, sorting, and browser-backed views
* GeoJSON / KML / CSV generation
* Designed for both **CLI usage** and **importable Python modules**

Ideal for HMDB uploads, OpenStreetMap contributions, field research, and road trip planning.

---

## ❗Important Note❗
First and foremost, I wanted to be completely transparent and say that there is a lot of vibe coding in here. If you go through the commit history you will see that I was working on this for a year and a half. I wrote the core logic in a Jupyter notebook and then slowly started to refactor it into a CLI tool. After that, I started learning AI agents and began refactoring and building the code into what it is today. 

In Redit and the forums people give a lot of crap for vibe-coding so I wanted to be upfront about it. I did a lot of work, and continue to do a lot of work on this project - with the goal of creating an accurate and comprehensive database of Texas Historical Markers.

---

## ⚡ Quickstart

```sh
cd pythonLib
pip install -e ".[dev]"
thc --help
make verify
```

Sample run:

```sh
thc counties --input ../atlas_db.csv --output UnmappedMarkersPerCounty --stats
```

---

## 📦 Installation

Install locally in editable mode to enable CLI commands:

```sh
cd pythonLib      # root project folder
pip install -e .
```

This installs commands system-wide while allowing live code edits with no reinstall.

System tools used by `thc viewcsv` pretty mode:

- `column`
- `less`

If unavailable, the command falls back to raw table output.

---

## 📁 Project Layout

```sh
pythonLib/
├─ pyproject.toml
├─ README.md
└─ thc_toolkit/
   ├─ utils.py            ← shared library: Atlas/OSM helpers (importable!)
   ├─ counties_cli.py     ← CLI tool: unmapped-per-county export
   ├─ route_cli.py        ← CLI tool: route marker proximity + map creation
   ├─ osm_cli.py          ← CLI tool: OSM/JOSM node creation + sync workflow
   ├─ sqlite_sync.py      ← CLI tool: CSV / SQLite build-export-verify workflow
   ├─ cli.py              ← unified entrypoint
   └─ __init__.py
```

⭐ Functions in `utils.py` are reusable from your own Python scripts.

---

## 🚀 CLI Usage

Canonical command is `thc` with subcommands:

```
thc counties      # Unmapped-per-county CSV export utilities
thc route         # Route-based filtering, mapping, exports
thc map           # County/city marker mapping
thc viewcsv       # CSV inspection in terminal
thc convertHMDB   # HMDB CSV -> THC format conversion
thc sqlite        # CSV / SQLite sync tools
thc-browser      # One-command SQLite browser launcher
```

Script aliases are also installed for compatibility:

```
counties
routes
osm
```

---

### 1) County Filtering & Export

Export unmapped markers (not private, not missing):

```sh
thc counties --input ../atlas_db.csv --output UnmappedMarkersPerCounty
```

Additional options:

```sh
thc counties --county Denton --input ../atlas_db.csv
thc counties --stats --input ../atlas_db.csv
thc counties --merge combined.csv --input ../atlas_db.csv
thc counties --summary-json summary.json --input ../atlas_db.csv
```

Defaults:

| Parameter | Default |
|---|---|
| Input CSV | auto-detected from `data.csv`, `atlas_db.csv`, `../atlas_db.csv`, `scripts/data.csv`, `../scripts/data.csv` |
| Output directory | `UnmappedMarkersPerCounty/` |

---

### 2) Route-Based Marker Mapping

Generate an interactive map of markers near a KML route:

```sh
thc route --track ../scripts/test.kml --data ../atlas_db.csv
```

Only unmapped:

```sh
thc route --track ../scripts/test.kml --data ../atlas_db.csv --unmapped
```

Export variants:

```sh
thc route --track ../scripts/test.kml --data ../atlas_db.csv --csv
thc route --track ../scripts/test.kml --data ../atlas_db.csv --geojson --kml
thc route --track ../scripts/test.kml --data ../atlas_db.csv --openmap   # auto-launch browser
```

Output files include:

| Output | Trigger |
|---|---|
| near_route_map_*.html | always |
| near_route_*.csv | `--csv` |
| combined_route_markers_*.geojson | `--geojson` |
| THC_markers_route_*.kml | `--kml` |

---

### 3) OSM/JOSM Integration (`utils.py` + `osm_cli.py`)

Convert atlas rows into OSM nodes → push to JOSM → update atlas flags.

#### Generate nodes:

```sh
osm create-nodes --csv ../atlas_db.csv --out nodes.json
```

Restrict to HMDB-sourced markers that are not yet in OSM
(rows where `isHMDB=True` and `isOSM=False`):

```sh
osm create-nodes --csv ../atlas_db.csv --out nodes.json --only-missing-osm
```

Run a duplicate pre-check against live OSM (queries Overpass for nearby
`memorial=plaque` nodes and fuzzy-matches the name). Matches are removed
from `nodes.json` and written to a review report:

```sh
osm create-nodes --csv ../atlas_db.csv --out nodes.json \
    --only-missing-osm \
    --dedup-check \
    --dedup-distance-ft 100 \
    --dedup-name-similarity 0.80 \
    --dedup-report nodes_skipped_for_review.json
```

Push to JOSM via Remote Control:

```sh
osm push-josm --nodes nodes.json
```

`nodes.json` is generated by the previous command.

Find markers missing in OSM:

```sh
osm find-missing --csv ../atlas_db.csv --geo /path/to/osm_extract.geojson
```

Update `isOSM` column and write results (legacy, no `OsmNodeID`):

```sh
osm update-isOSM --csv ../atlas_db.csv --nodes nodes.json --out updated.csv
```

Reconcile against live OSM after a JOSM Upload — sets both `isOSM=True`
and `OsmNodeID` on matched rows (preferred):

```sh
osm sync-from-osm --csv ../atlas_db.csv --nodes nodes.json --out updated.csv \
    --batch-size 50 --rate-limit-sec 1.5 --report sync_report.json
```

Notes:

- `osm_extract.geojson` should be a GeoJSON export of current OSM markers (for example, via Overpass).
- `updated.csv` is created by `update-isOSM` / `sync-from-osm`.
- `push-josm` only stages nodes locally in JOSM. You must Upload from JOSM
  before `sync-from-osm` can see the new OSM IDs.

#### Correcting wrong `ref:US-TX:thc` values in OSM

When existing OSM nodes carry the wrong `ref:US-TX:thc` (the atlas is the
source of truth), two subcommands push corrections in batches. Both share
the same plan CSV (`id,correct_ref,...`) and the same JSON state file —
state survives across runs so reruns skip already-handled IDs.

JOSM-staged mode (review each tag change in JOSM, then click Upload):

```sh
thc osm refix-osm-ids \
    --plan ../scripts/tmp/osm_refix_plan.csv \
    --state ../scripts/tmp/osm_refix_state.json \
    --batch-size 25
```

Each row issues a `/load_object?objects=nID&addtags=ref:US-TX:thc=N` call to
JOSM Remote Control on `localhost:8111` (JOSM must be running with a data
layer open). Only `ref:US-TX:thc` is added/overwritten; no other tags are
touched.

Direct-to-OSM mode (no JOSM review; one changeset per batch):

```sh
thc osm refix-osm-direct \
    --plan ../scripts/tmp/osm_refix_plan.csv \
    --state ../scripts/tmp/osm_refix_state.json \
    --batch-size 50 --repeat 80 --rate-limit-sec 2.0
```

Reads the OAuth2 token JOSM stored under
`~/.config/JOSM/preferences.xml` (scope `write_api` required). The token is
not stored in the repo. Each batch opens a bot-flagged changeset with
`source=atlas.thc.texas.gov; hmdb.org`, fetches the current node state in
bulk, mutates only `ref:US-TX:thc`, uploads the diff, and closes the
changeset.

Flags worth knowing:

| Flag | Purpose |
|---|---|
| `--dry-run` | Print what would be pushed without contacting JOSM/OSM |
| `--repeat N` | Run N batches back-to-back in one invocation (direct mode) |
| `--rate-limit-sec` | Sleep between batches; default 1.0s (direct), 0.4s (JOSM) |
| `--changeset-comment` | Override the default mass-edit comment (direct mode) |

Recommended cadence: start with `refix-osm-ids --batch-size 5` to validate
the plan against a handful of cases in JOSM, then graduate to
`refix-osm-direct --batch-size 50` for the bulk. For mass edits over ~1000
nodes, post a courtesy notice on the talk-us-texas mailing list first.

---

### 4) CSV / SQLite Sync

Keep `atlas_db.csv` as the source of truth and use SQLite as the generated working copy.

Rebuild SQLite from CSV:

```sh
thc sqlite build --csv ../atlas_db.csv --sqlite ../atlas_db.sqlite
```

Use `--strict-ids` if you want the build to fail on duplicate canonical IDs.

Export CSV back from SQLite:

```sh
thc sqlite export --sqlite ../atlas_db.sqlite --csv atlas_db_roundtrip.csv
```

Verify row counts and key columns stay aligned:

```sh
thc sqlite verify --csv ../atlas_db.csv --sqlite ../atlas_db.sqlite
```

Open the browser viewer:

```sh
thc sqlite browse
```

Or use the direct launcher:

```sh
thc-browser
```

---

## 🔥 Import as a Python Library

The new shared **utils module** allows direct scripting:

```python
from thc_toolkit.utils import read_atlas, create_nodes, push2josm

df = read_atlas("../atlas_db.csv")
nodes = create_nodes(df)
refs = push2josm(nodes)
```

Or still call full CLI flows programmatically:

```python
from thc_toolkit import counties_cli, route_cli, osm_cli
```

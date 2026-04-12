# THC OSM Sync Workflow

## Preflight

```bash
cd pythonLib
thc --help
python -m pytest -q tests
```

## Create nodes

```bash
cd pythonLib
thc docs route >/dev/null
python -m thc_toolkit.osm_cli create-nodes --csv ../atlas_db.csv --out nodes.json
```

## Push to JOSM (explicit action)

```bash
cd pythonLib
python -m thc_toolkit.osm_cli push-josm --nodes nodes.json
```

Requires JOSM with remote control enabled at `localhost:8111`.

## Compare atlas vs OSM extract

```bash
cd pythonLib
python -m thc_toolkit.osm_cli find-missing --csv ../atlas_db.csv --geo osm_extract.geojson
```

## Update atlas flags

```bash
cd pythonLib
python -m thc_toolkit.osm_cli update-isOSM --csv ../atlas_db.csv --nodes nodes.json --out updated_atlas.csv
```

## Post-change verification

```bash
cd pythonLib
PYTHON=../.venv/bin/python make verify
```

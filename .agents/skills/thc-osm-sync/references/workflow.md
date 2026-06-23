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

### Scope to HMDB markers not yet in OSM

Use `--only-missing-osm` to restrict node generation to rows where
`isHMDB=True` and `isOSM=False`. Rows with `NA` in either flag are excluded.

```bash
cd pythonLib
python -m thc_toolkit.osm_cli create-nodes \
    --csv ../atlas_db.csv \
    --out nodes.json \
    --only-missing-osm
```

### Dedup pre-check against live OSM

Use `--dedup-check` to query Overpass for existing `memorial=plaque` nodes
within `--dedup-distance-ft` (default 100 ft) of each candidate. Candidates
whose name fuzzy-matches an existing node (default >= 0.80 normalized
similarity) are removed from `nodes.json` and recorded in
`--dedup-report` (default `nodes_skipped_for_review.json`) for manual
follow-up.

```bash
cd pythonLib
python -m thc_toolkit.osm_cli create-nodes \
    --csv ../atlas_db.csv \
    --out nodes.json \
    --only-missing-osm \
    --dedup-check \
    --dedup-distance-ft 100 \
    --dedup-name-similarity 0.80 \
    --dedup-report nodes_skipped_for_review.json \
    --dedup-rate-limit-sec 1.0
```

Each entry in the skipped report contains the candidate (name, lat/lon,
refs) and the matched OSM node (id, name, tags, distance in feet, name
similarity). Review the report before pushing; if a match is a false
positive, re-run with `--only-missing-osm` and either relax the threshold,
shrink the radius, or filter the input CSV to the specific row(s) you want
to keep.

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

### Authoritative: `sync-from-osm` (post-upload reconciliation)

After you Upload from JOSM and the changes propagate (usually < 1 min),
query Overpass for each `ref:US-TX:thc` in `nodes.json` and stamp both
`isOSM=True` AND `OsmNodeID` on the matched atlas rows. Refs not yet
visible in OSM are left alone — safe to re-run.

```bash
cd pythonLib
python -m thc_toolkit.osm_cli sync-from-osm \
    --csv ../atlas_db.csv \
    --nodes nodes.json \
    --out updated_atlas.csv \
    --batch-size 50 \
    --rate-limit-sec 1.5 \
    --report sync_report.json
```

The optional `--report` JSON lists matched refs (→ OSM IDs), unresolved
refs (not yet found in OSM), and refs from the mapping that didn't match
any atlas row.

### Legacy: `update-isOSM` (local flip only, no OsmNodeID)

```bash
cd pythonLib
python -m thc_toolkit.osm_cli update-isOSM --csv ../atlas_db.csv --nodes nodes.json --out updated_atlas.csv
```

This blindly sets `isOSM=True` for every ref in `nodes.json` regardless of
whether it actually made it into OSM, and does not populate `OsmNodeID`.
Prefer `sync-from-osm` for normal workflows.

## Post-change verification

```bash
cd pythonLib
PYTHON=../.venv/bin/python make verify
```

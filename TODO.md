# TODO

Future work and enhancements for the Texas Historical Markers project.

## Data Collection & Sync

- [ ] Create a skill/script that pulls the latest Texas marker information from hmdb.org and updates the local atlas database with new entries, changed coordinates, and updated metadata.

## OSM Data Hygiene

- [ ] Backfill `operator:wikidata=Q2397965` on every TX `memorial=plaque` node that is a THC marker but is missing the tag. Approach: bulk-fetch all TX `memorial=plaque` nodes from Overpass, classify each as THC vs non-THC (cross-check `ref:US-TX:thc` / `memorial:website` hmdb.org link / name fuzzy-match against `atlas_db.csv`), build a plan CSV, push corrections via `thc osm refix-osm-direct` style flow (one tag-add per node, preserve all other tags). 2026-06-27 snapshot: 508 of 11,782 nodes (4.3%) lack the tag.


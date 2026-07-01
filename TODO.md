# TODO

Future work and enhancements for the Texas Historical Markers project.

## Data Collection & Sync

- [x] ~~Create a skill/script that pulls the latest Texas marker information from hmdb.org and updates the local atlas database with new entries, changed coordinates, and updated metadata.~~ **Done 2026-06-29** — `thc hmdb fetch` + `hmdb-fetch` skill.

## OSM Data Hygiene

- [x] ~~Backfill `operator:wikidata=Q2397965` on every TX `memorial=plaque` node that is a THC marker but is missing the tag.~~ **Done 2026-06-30** — 51 nodes tagged in changesets 184890336 / 184890339 / 184890342. 3 same-name-but-far-away skipped; 5 unverifiable (atlas has no coord) skipped. Most of the original 508 backlog was already backfilled by the community between the 2026-06-27 snapshot and today.


# Standing decisions for an hmdb update

Joe's rulings, with the date they were given. Apply them without asking;
ask only for the cases marked *ask*.

## Report → plan

| report finding | action |
|---|---|
| `auto_applied.csv` row, coordinate distance small | link (reconcile does it); nothing to ask |
| auto row with hmdb↔atlas distance > 2 km but same street address | link; the atlas coord was a bad geocode (Sand Lake 2026-09-06, 30 km) — note it in the plan |
| `review_candidates.csv`, punctuation/abbreviation/diacritic-only difference | approve `YES` |
| candidate whose atlas row is `isActive=False` | `NO`: superseded record; the active sibling already links the page (Stephenville brick streets) |
| `review_name_mismatches.csv` with same Marker No., county, address and coordinate | approve; a "Former Site of …" prefix on hmdb is still the same marker (2026-09-06). Joe may rename the atlas row to hmdb's title by hand |
| `review_hmdb_conflicts.csv` where the atlas id is dead in the export | re-catalogue: swap `ref:hmdb` + `memorial:website` (+ DATA_NOTE, + OSM node tags) |
| conflict where the atlas id is still live | genuine second page: `hmdb_ignore.csv`, never a second atlas row (see feedback_hmdb_ignore_list_convention) |
| dead ref, *not yet published* | Joe's own pending submission — leave it; it will appear in a later export |
| dead ref, id above the export max | post-pull entry — leave it |
| dead ref, *gone* with no successor | clear `ref:hmdb`/`memorial:website`, `isHMDB=False`, DATA_NOTE (project_hmdb_id_replacements) |
| hmdb-only page whose Marker No. is unknown to THC but a same-county un-linked atlas row matches on name, year and coordinate | hmdb typo'd the number: link that atlas row by MarkerID with the full enrichment, DATA_NOTE the typo (Smith Cemetery 7150→15483, 2026-09-06) |
| hmdb-only page with no Marker No. and no atlas match | *ask*, but the 2026-09-06 answer was "add it": new row at the end of the file keyed on `ref:hmdb` only, following the Richard Williams (hmdb 307955) row — `isActive=True`, RTHL False, `thc:designation=Historical Marker`, Marker Notes = hmdb location + erector + "Not in the THC Atlas database", Marker Text = the hmdb inscription, DATA_NOTE says why |
| Missing flip: hmdb *Reported Missing* | `isMissing=True`, keep the OSM node (2026-09-06) |
| Missing flip: hmdb *Confirmed Missing* | `isMissing=True`, keep the OSM node (Saint Paul Baptist 2026-09-06). Garland 2026-09-01 was deleted because hmdb had also re-catalogued it; do not treat that as the rule |
| Missing flip: atlas True, hmdb blank, THC "In Situ" | accept hmdb, `isMissing=False` (Monterey High School 2026-09-06) |
| working tree has LibreOffice coordinate churn plus real edits | restore the churn, keep the real edits, before any write (2026-09-05, 2026-09-06) |
| Joe says he already edited rows by hand (re-catalogue swaps, links) | keep his values; add the DATA_NOTE and finish the enrichment fields he skipped (addr:city, isPending, Marker Notes) |
| reconcile replaced a weebly-sourced `verified:*` coordinate | append a DATA_NOTE with the old value and distance (22 rows on 2026-09-06, up to 226 m) |

## OSM

| situation | action |
|---|---|
| re-catalogued id on a row with an OSM node | `retag_nodes.py --swap THC:OLD:NEW` — refs only |
| newly linked row that already has an OSM node | `retag_nodes.py --link THC` — refs, addr, start_date, operator; never name/inscription/material; leave geometry when the hmdb coord is within ~10 m |
| newly linked rows without a node | `push_new_nodes.py` after the atlas write; Joe's default is "push the new additions into OSM" (2026-09-06) |
| dedup hit: plaque node with the atlas Details URL in `website` and no `ref:US-TX:thc` | it is ours — `--adopt THC=NODE` (Rex Ingram n9525057348, 2026-09-06; Laredo 2026-08-22) |
| dedup hit: node already holds the ref | not a create; investigate which node is right (feedback_validate_the_post_state) |
| node for a row Joe linked to a *not yet published* hmdb page | create it; `memorial:website` will resolve once hmdb publishes (Gober Cemetery 2026-09-06) |
| DuPree-style legislative markers (SB 667 series, no THC number) | node with `note=Marker is not present in THC Atlas database`, no `ref:US-TX:thc`, no `website` |

## Always

- Table for Joe: **name, expected ref:thc, hmdb url** (+ a kind column). He
  wants to see it before anything is added.
- No git commit unless he asks.
- Overpass main endpoint is flaky; the scripts fall back automatically.

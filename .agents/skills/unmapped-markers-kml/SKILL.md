---
name: unmapped-markers-kml
description: County-scoped tooling for THC markers that have not been entered into hmdb.org. Two modes - (1) build a Google My Maps-ready KML for field hunting, (2) audit stored estimated:Latitude/Longitude against the US Census Geocoder and flag rows where the address disagrees with the stored coord by more than 0.5 mi. Use whenever the user asks to "map unmapped markers in XX county" or "audit/verify unmapped coords in XX county".
---

# Unmapped markers — KML build + coord audit

County-scoped tooling for THC historical markers that have not yet been
entered into hmdb.org. "Unmapped" means `ref:hmdb` is empty.

Two modes, both filter on the same row population and write to the
`unmapped markers/` directory (tracked in git):

| Mode  | Script                   | Output                                             |
|-------|--------------------------|----------------------------------------------------|
| Build (one county) | `build_kml.py`      | KML for import into mymaps.google.com              |
| Build (all, incremental) | `build_all_counties.py` | Rebuilds only changed counties; prunes emptied ones |
| Build (statewide, one file) | `build_statewide_kml.py` | ONE KML for all of Texas, folder-split for My Maps |
| Build (mapped markers) | `build_mapped_kml.py` | ONE KML of every marker with a field-verified coord |
| Audit | `audit_coords.py`   | CSV review of rows whose stored coord disagrees with the geocoded address |

## When to run this skill

Build-mode trigger phrases:
- "map the unmapped markers in <county> county"
- "build a KML for unmapped <county> markers"
- "I want to go marker hunting in <county>"

Audit-mode trigger phrases:
- "audit the unmapped coords in <county>"
- "compare addresses to thc:lat/lon for <county>"
- "find <county> unmapped markers where the address and coord disagree"

The build mode excludes `isMissing=True` markers (no point hunting for
ones already confirmed missing), `isPrivate=True` markers (no point
hunting for ones on private property), and `isActive=False` markers
(superseded or duplicate THC atlas records — the same physical marker is
documented under another thc#, which usually already carries a
`ref:hmdb`). The audit mode does **not** filter on `isMissing` or
`isPrivate` — comparing stored coord to address is useful regardless.

The `isActive=False` exclusion matters because such a row has no `ref:hmdb`
of its own and therefore *looks* unmapped, while the marker it describes
is already recorded. Example: thc#15237 "First Presbyterian Church, USA,
of Garland" is a duplicate record of thc#6702, which carries hmdb 148087
and an OSM node — hunting it would be a wasted trip.

## How to run

Both scripts run from the repo root so `--atlas atlas_db.csv` resolves.

### Build mode — KML for Google My Maps

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/build_kml.py --county "Tarrant"
```

Options:
- `--county <name>` — required, exact `addr:county` value (case-sensitive)
- `--atlas <path>` — default `atlas_db.csv`
- `--out-dir <path>` — default `unmapped markers`
- `--no-write-coords` — do not persist geocoded coords to atlas_db.csv

### Build mode — every county, incrementally

To (re)build KMLs for **all** counties, use `build_all_counties.py`. It
wraps `build_kml.py` and only rebuilds counties whose KML-eligible rows
changed since the last run (per-county content hash in a state file), so
routine refreshes take seconds instead of a minute-plus. Nominatim is
**disabled by default** (the workflow pre-geocodes via the Census batch);
pass `--geocode` to re-enable it.

```bash
# incremental: rebuild only changed counties, prune emptied ones
python3 .agents/skills/unmapped-markers-kml/scripts/build_all_counties.py

# force a full rebuild of every county
python3 .agents/skills/unmapped-markers-kml/scripts/build_all_counties.py --all
```

Options:
- `--all` / `--force` — rebuild every county, ignoring change detection
- `--county <name>` — limit to specific counties (repeatable); skips state write
- `--geocode` — enable Nominatim geocoding (default off)
- `--no-prune` — keep KMLs for counties that now have zero eligible rows
- `--atlas <path>` — default `atlas_db.csv`
- `--out-dir <path>` — default `unmapped markers`
- `--state <path>` — default `<repo>/scripts/tmp/kml_build_state.json` (gitignored)

Behavior: new/changed counties are rebuilt; unchanged counties are
skipped; counties that drop to zero eligible rows have their stale KML +
`_no_coords.txt` sidecar pruned. On the first run (no state file) every
county is built and the state is seeded.

### Build mode — one statewide KML

When the ask is "all of Texas in a single file" rather than a county at a
time, use `build_statewide_kml.py`. It emits one KML plus a no-coord
sidecar and never touches `atlas_db.csv`.

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/build_statewide_kml.py
```

Options:
- `--atlas <path>` — default `atlas_db.csv`
- `--out <path>` — default `unmapped markers/Texas_statewide_unmapped.kml`
- `--sidecar <path>` — default `unmapped markers/Texas_statewide_no_coords.txt`
- `--max-per-folder <int>` — default 2000, the My Maps per-layer cap

Three deliberate differences from the county build:
- **No geocoding.** A statewide pass would be thousands of Nominatim
  requests. Coord-less rows go to the sidecar; pre-geocode per county
  with `build_kml.py` if you want them on the map.
- **`verified:*` beats `estimated:*`.** A field-measured coord is used
  when present, which puts a handful of rows on the map that the
  county build (estimated-only) drops.
- **Folder split.** Google My Maps imports each KML `<Folder>` as a layer
  and silently truncates a layer past 2,000 rows, so counties are packed
  alphabetically into folders under that cap. Counties are never split
  across folders.

Do **not** name the output `<something>_unmapped_markers.kml` —
`build_all_counties.py` globs that pattern and prunes any prefix that is
not a real county, so the statewide file would be deleted on the next
incremental run.

### Build mode — the mapped markers (inverse of the other two)

`build_mapped_kml.py` maps the rows that already have a field-verified
coordinate (`verified:Latitude` + `verified:Longitude`) — a coverage /
reference layer rather than a hunting list.

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/build_mapped_kml.py

# the one that actually imports into Google My Maps: two files, ~3 MB each
python3 .agents/skills/unmapped-markers-kml/scripts/build_mapped_kml.py \
    --no-marker-text --split 2 --out generated/Texas_mapped_markers_slim.kml

# slim + zipped: 0.7 MB, for transport (NOT for My Maps -- see below)
python3 .agents/skills/unmapped-markers-kml/scripts/build_mapped_kml.py \
    --no-marker-text --kmz --out generated/Texas_mapped_markers_slim.kml
```

Options:
- `--atlas <path>` — default `atlas_db.csv`
- `--out <path>` — default `generated/Texas_mapped_markers.kml`
- `--no-marker-text` — drop Marker Text from popups (~16 MB → ~6 MB)
- `--kmz` — write a zipped `.kmz` (`doc.kml` inside) instead of a plain
  `.kml`; the `--out` suffix is swapped for you. Combined with
  `--no-marker-text` this lands at ~0.7 MB, a 23x reduction
- `--split N` — write N files named `<stem>_partIofN`, cut west to east
  into equal marker counts with counties kept whole
- `--max-per-folder <int>` — default 2000, the My Maps per-layer cap

Note that `Marker Notes` on 66 kept rows still reads "reported missing".
That text is **THC's**, copied verbatim from the `Loc_Desc` column of the THC
export — it is not an HMDB signal. All 66 have an HMDB page and HMDB's own
`Missing` column is blank for every one, so `isMissing=False` is correct and
these belong on the map. `isMissing` is authoritative here, never the note
text.

It differs from the unmapped builds on purpose:
- **`isMissing=True` excluded, `isPrivate` and `isOSM=False` kept.**
  Missing markers are dropped for the same reason as every other builder
  here — a marker that is gone is not coverage. This is a standing rule
  across every map this skill emits, not a per-build choice: no flag opts
  back in. Private and off-OSM rows
  stay, since hiding them would misrepresent coverage; they are
  distinguished by pin colour *and* a name prefix (the same belt-and-braces
  the `[PENDING]` convention uses, in case a renderer flattens styles):
  green = on OSM, blue = `[NO OSM NODE]`, purple = `[PRIVATE]`.
  Precedence: private > no-OSM.
- **One `<Folder>` per county** (258 of them), for a browsable tree in
  Google Earth / QGIS. This is *not* a My Maps layout — see below.
- **HMDB and OSM links in the popup.** These markers are documented, so
  the links are the point. `thc:designation` and the THC Atlas link stay
  out, per the tuning note below.
- **Output goes to `generated/`, which is gitignored.** At ~16 MB it is a
  derived artifact that rebuilds from `atlas_db.csv` in seconds; it does
  not belong in git history the way the per-county KMLs do.

### Getting this into Google My Maps

My Maps enforces four separate caps, and this dataset trips three of them:

| cap | value | consequence here |
|-----|-------|------------------|
| file size | 5 MB | **measured on the UNZIPPED kml** |
| features per layer | 2,000 | silently truncated past it |
| layers per map | 10 | — |
| features per map | 10,000 | 12,678 will not fit in one map |

**A `.kmz` does not get you under the size cap.** My Maps unzips first and
then applies the 5 MB limit to the `doc.kml` inside, so a 0.7 MB kmz holding
a 6.4 MB kml is rejected with a size error that looks wrong until you know
this. Confirmed the hard way on 2026-08-18. Use `--split`, not `--kmz`, to
get under 5 MB.

The combination that imports:

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/build_mapped_kml.py \
    --no-marker-text --split 2 --out generated/Texas_mapped_markers_slim.kml
```

~3.1 MB and ~2.9 MB unzipped, 4 folders each (so 4 layers, under the 10-layer
cap), no folder over 2,000. Because 6.5k + 6.2k exceeds the 10,000-per-map
cap, **each part needs its own map** — they cannot be layered into one.

Note the parts overlap slightly in longitude: the cut is on each county's
mean longitude with counties kept whole, so a wide county can carry
individual pins past the seam.

For a single file, use Google Earth, QGIS, or OsmAnd, none of which have
these limits.

### Audit mode — flag rows where address disagrees with stored coord

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/audit_coords.py --county "Tarrant"
```

Options:
- `--county <name>` — required
- `--atlas <path>` — default `atlas_db.csv`
- `--out <path>` — default `unmapped markers/<county>_coord_audit_review.csv`
- `--threshold-mi <float>` — default `0.5`

## What build_kml.py does

1. **Filter** atlas_db.csv to `addr:county == <county>` AND
   `ref:hmdb` empty AND `isMissing != True` AND `isPrivate != True`
   AND `isActive != False`.
2. **Direct map**: rows with `estimated:Latitude` + `estimated:Longitude` go straight
   into the KML.
3. **Geocode**: rows with no coords but a street-level address
   (`addr:full` contains a digit) get geocoded via OSM **Nominatim**
   (1 req/sec, polite User-Agent).
4. **Write-back**: by default geocoded coords are written back into
   `estimated:Latitude`/`estimated:Longitude` so the next run skips the lookup. Pass
   `--no-write-coords` to skip this.
5. **Pending flag**: rows with `isPending=True` get an **orange pin**
   (`<styleUrl>#pending</styleUrl>` → `ms/icons/orange-dot.png`) plus
   `[PENDING]` prefixed on the KML `<name>` and a warning paragraph at the
   top of the `<description>`. Everything else uses `#normal` (red). The
   colour is the point — a pending marker is visible as "don't drive out
   for this yet" without opening the popup.

   If Google My Maps ever flattens the imported icon styles, the
   `[PENDING]` name prefix is still there, and My Maps can style by it
   manually. Keep both signals for that reason.
6. **Description content** (per placemark): Marker Notes → Address →
   (geocoded match note, if applicable) → full Marker Text. Designation
   and Atlas links are intentionally omitted — the user found them noisy.

   **`Marker Notes` yes, `DATA_NOTE` never.** `Marker Notes` is written for
   the person trying to find the marker — directions, landmarks, what to
   look for. `DATA_NOTE` is for whoever maintains the data: coordinate
   provenance, duplicate adjudications, sync history. It is noise to
   somebody standing at a roadside and must stay out of the popup. If
   data-management text ever turns up inside `Marker Notes`, move it to
   `DATA_NOTE` rather than filtering it here.
7. **Sidecar**: rows with no coords AND no usable address are dumped to
   `<county>_unmapped_no_coords.txt` so the user can locate them manually.

## What audit_coords.py does

1. **Filter** atlas_db.csv to `addr:county == <county>` AND `ref:hmdb`
   empty AND has `estimated:Latitude` + `estimated:Longitude` AND has a street-level
   `addr:full` (contains a digit). (No `isMissing` filter here.)
2. **Batch-geocode** all candidate addresses in a single POST to the US
   Census batch geocoder
   (`https://geocoding.geo.census.gov/geocoder/locations/addressbatch`,
   `benchmark=Public_AR_Current`). One HTTP call for all 60–80 rows;
   no per-request rate limiting to worry about.
3. **Compute Haversine distance** between the stored
   `estimated:Latitude`/`estimated:Longitude` and the Census-returned coord.
4. **Flag** rows where distance > `--threshold-mi` (default 0.5) into
   `<county>_coord_audit_review.csv`, sorted by distance descending.
5. **Report** unmatched rows (Census couldn't geocode) to stdout so the
   human can fix the address — typical causes are "100 block of X",
   park-name prefixes, double commas, "Inside Six Flags".

## Output

Files land in `unmapped markers/`, which is **tracked in git** — a rebuild
shows up as a real diff, so review it like any other change:

| file                                       | meaning                                                                  |
|--------------------------------------------|--------------------------------------------------------------------------|
| `<county>_unmapped_markers.kml`            | build mode — import into Google My Maps                                  |
| `<county>_unmapped_no_coords.txt`          | build mode — city-only markers needing manual location work              |
| `<county>_coord_audit_review.csv`          | audit mode — rows whose stored coord disagrees with the geocoded address |
| `Texas_statewide_unmapped.kml`             | statewide build — every unmapped marker in Texas, one file              |
| `Texas_statewide_no_coords.txt`            | statewide build — markers with no coordinate at all                      |
| `generated/Texas_mapped_markers.kml`       | mapped build — every marker with a field-verified coord (gitignored)     |
| `generated/Texas_mapped_markers_slim.kmz`  | mapped build — same pins, no Marker Text, zipped (~0.7 MB, gitignored)   |
| `generated/..._slim_part{1,2}of2.kml`      | mapped build — the My Maps-importable split, ~3 MB each (gitignored)     |

## Import flow (for the user)

1. https://www.google.com/mymaps → **Create a New Map**
2. **Import** → drop the .kml
3. Google auto-detects `<name>` as the title and renders the HTML in
   `<description>` as the popup body.

## Geocoders used

- **build_kml.py** uses **OSM Nominatim** for the small number of rows
  that lack stored coords. Per their usage policy: ≤1 req/sec with a
  polite User-Agent. Do not parallelize. Be aware that running the build
  repeatedly across multiple counties can trip Nominatim's anti-abuse
  throttle (HTTP 429); when that happens, wait it out or switch to the
  Census Geocoder for that run.
- **audit_coords.py** uses the **US Census batch geocoder**. One HTTP
  POST handles all ~60+ rows at once, so there is no per-request rate
  limiting. Census covers US addresses only — fine for Texas.

## Guardrails

- **Geocoded coords are approximate** — `build_kml.py` flags this in each
  geocoded placemark's description (`Coordinates derived by geocoding the
  address — may be approximate`). Treat them as a starting point for the
  user's field visit, not survey-grade.
- **Atlas write-back** (build mode only): the script edits `atlas_db.csv`
  in place using csv.writer with `lineterminator="\n"` to preserve LF
  endings. Review the diff before committing if the user is conscious of
  atlas hygiene.
- **City-only addresses are skipped** for geocoding — they would just
  snap to the city centroid, which is not useful for field hunting.
- **Audit may double-flag a previously-geocoded row**: if `build_kml.py`
  wrote a Nominatim-derived coord back to atlas, the audit will compare
  that against the Census-derived coord — small disagreements between
  the two geocoders are expected and typically fall well under the
  0.5 mi threshold.
- **Census "no match" usually means the address itself is malformed** —
  block-only addresses ("1300 block of X"), park-name prefixes, trailing
  punctuation. Fix the address in `atlas_db.csv` and re-run.

## Tuning history (decisions captured for future runs)

- `isMissing=True` excluded — user does not want to chase missing markers.
- `isPrivate=True` excluded — user does not want to chase markers on private
  property.
- `isActive=False` excluded (2026-08-15, column renamed from `isTHC` the same day) — Joe spotted thc#15237 in the Dallas
  KML, a duplicate record of thc#6702 whose marker is already photographed on
  hmdb. Empty `ref:hmdb` is a proxy for "not on hmdb" that fails for
  superseded/duplicate THC records, since the *marker* is recorded even though
  the *row* has no id. 3 such rows statewide, all in Dallas: thc#6692,
  thc#6711, thc#15237.
- `thc:designation` and the THC Atlas link removed from the popup body —
  noise.
- Geocoded coords persist back to `atlas_db.csv` by default so the lookup
  is amortized across future runs.
- `isPending=True` flagged with `[PENDING]` prefix + warning paragraph so
  the user does not waste time looking for a marker that has not yet been
  installed.

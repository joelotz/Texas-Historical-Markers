---
name: unmapped-markers-kml
description: County-scoped tooling for THC markers that have not been entered into hmdb.org. Two modes - (1) build a Google My Maps-ready KML for field hunting, (2) audit stored thc:Latitude/Longitude against the US Census Geocoder and flag rows where the address disagrees with the stored coord by more than 0.5 mi. Use whenever the user asks to "map unmapped markers in XX county" or "audit/verify unmapped coords in XX county".
---

# Unmapped markers — KML build + coord audit

County-scoped tooling for THC historical markers that have not yet been
entered into hmdb.org. "Unmapped" means `ref:hmdb` is empty.

Two modes, both filter on the same row population and write to the
`unmapped markers/` directory (gitignored):

| Mode  | Script              | Output                                             |
|-------|---------------------|----------------------------------------------------|
| Build | `build_kml.py`      | KML for import into mymaps.google.com              |
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
ones already confirmed missing). The audit mode does **not** filter on
`isMissing` — comparing stored coord to address is useful regardless.

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
   `ref:hmdb` empty AND `isMissing != True`.
2. **Direct map**: rows with `thc:Latitude` + `thc:Longitude` go straight
   into the KML.
3. **Geocode**: rows with no coords but a street-level address
   (`addr:full` contains a digit) get geocoded via OSM **Nominatim**
   (1 req/sec, polite User-Agent).
4. **Write-back**: by default geocoded coords are written back into
   `thc:Latitude`/`thc:Longitude` so the next run skips the lookup. Pass
   `--no-write-coords` to skip this.
5. **Pending flag**: rows with `isPending=True` get `[PENDING]` prefixed
   on the KML `<name>` and a warning paragraph at the top of the
   `<description>` so the user knows the marker may not yet be installed.
6. **Description content** (per placemark): Marker Notes → Address →
   (geocoded match note, if applicable) → full Marker Text. Designation
   and Atlas links are intentionally omitted — the user found them noisy.
7. **Sidecar**: rows with no coords AND no usable address are dumped to
   `<county>_unmapped_no_coords.txt` so the user can locate them manually.

## What audit_coords.py does

1. **Filter** atlas_db.csv to `addr:county == <county>` AND `ref:hmdb`
   empty AND has `thc:Latitude` + `thc:Longitude` AND has a street-level
   `addr:full` (contains a digit). (No `isMissing` filter here.)
2. **Batch-geocode** all candidate addresses in a single POST to the US
   Census batch geocoder
   (`https://geocoding.geo.census.gov/geocoder/locations/addressbatch`,
   `benchmark=Public_AR_Current`). One HTTP call for all 60–80 rows;
   no per-request rate limiting to worry about.
3. **Compute Haversine distance** between the stored
   `thc:Latitude`/`thc:Longitude` and the Census-returned coord.
4. **Flag** rows where distance > `--threshold-mi` (default 0.5) into
   `<county>_coord_audit_review.csv`, sorted by distance descending.
5. **Report** unmatched rows (Census couldn't geocode) to stdout so the
   human can fix the address — typical causes are "100 block of X",
   park-name prefixes, double commas, "Inside Six Flags".

## Output

Files land in `unmapped markers/` (gitignored):

| file                                       | meaning                                                                  |
|--------------------------------------------|--------------------------------------------------------------------------|
| `<county>_unmapped_markers.kml`            | build mode — import into Google My Maps                                  |
| `<county>_unmapped_no_coords.txt`          | build mode — city-only markers needing manual location work              |
| `<county>_coord_audit_review.csv`          | audit mode — rows whose stored coord disagrees with the geocoded address |

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
- `thc:designation` and the THC Atlas link removed from the popup body —
  noise.
- Geocoded coords persist back to `atlas_db.csv` by default so the lookup
  is amortized across future runs.
- `isPending=True` flagged with `[PENDING]` prefix + warning paragraph so
  the user does not waste time looking for a marker that has not yet been
  installed.

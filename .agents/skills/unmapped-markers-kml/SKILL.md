---
name: unmapped-markers-kml
description: Build a Google My Maps-ready KML of unmapped THC markers for a single county. Use whenever the user asks to "map unmapped markers in XX county" or similar. Output is a KML the user imports into mymaps.google.com.
---

# Unmapped markers → KML (for Google My Maps)

Generates a county-scoped KML of THC historical markers that have not yet
been entered into hmdb.org so the user can hunt them down in person and
add them to HMDB. The KML is built to be dropped straight into
mymaps.google.com (Create New Map → Import).

There is no Google My Maps public API. The user manually imports the KML.

## When to run this skill

Trigger phrases include:
- "map the unmapped markers in <county> county"
- "build a KML for unmapped <county> markers"
- "I want to go marker hunting in <county>"

If the user says "unmapped" they mean `ref:hmdb` is empty. The script also
excludes `isMissing=True` markers (no point hunting for ones already
confirmed missing).

## How to run

```bash
python3 .agents/skills/unmapped-markers-kml/scripts/build_kml.py --county "Tarrant"
```

Run from the repo root so the default `--atlas atlas_db.csv` resolves
correctly. Output goes to `unmapped markers/` (gitignored).

Options:
- `--county <name>` — required, exact `addr:county` value (case-sensitive)
- `--atlas <path>` — default `atlas_db.csv`
- `--out-dir <path>` — default `unmapped markers`
- `--no-write-coords` — do not persist geocoded coords to atlas_db.csv

## What the script does

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

## Output

Files land in `unmapped markers/` (gitignored):

| file                                       | meaning                                        |
|--------------------------------------------|------------------------------------------------|
| `<county>_unmapped_markers.kml`            | import into Google My Maps                     |
| `<county>_unmapped_no_coords.txt`          | city-only markers needing manual location work |

## Import flow (for the user)

1. https://www.google.com/mymaps → **Create a New Map**
2. **Import** → drop the .kml
3. Google auto-detects `<name>` as the title and renders the HTML in
   `<description>` as the popup body.

## Guardrails

- **Nominatim rate limit**: the script sleeps 1.1 s between geocode
  requests per their usage policy. Do not parallelize.
- **Geocoded coords are approximate** — the script flags this in each
  placemark's description (`Coordinates derived by geocoding the address
  — may be approximate`). Treat them as a starting point for the user's
  field visit, not survey-grade.
- **Atlas write-back**: the script edits `atlas_db.csv` in place using
  csv.writer with `lineterminator="\n"` to preserve LF endings. Review
  the diff before committing if the user is conscious of atlas hygiene.
- **City-only addresses are skipped** for geocoding — they would just
  snap to the city centroid, which is not useful for field hunting.

## Tuning history (decisions captured for future runs)

- `isMissing=True` excluded — user does not want to chase missing markers.
- `thc:designation` and the THC Atlas link removed from the popup body —
  noise.
- Geocoded coords persist back to `atlas_db.csv` by default so the lookup
  is amortized across future runs.
- `isPending=True` flagged with `[PENDING]` prefix + warning paragraph so
  the user does not waste time looking for a marker that has not yet been
  installed.

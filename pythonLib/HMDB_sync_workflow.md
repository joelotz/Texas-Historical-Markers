# HMDB → atlas_db Sync Workflow

This document describes the end-to-end process for synchronising HMDB data into `atlas_db.csv` using a fresh export from hmdb.org. The scripts referenced below already exist in this directory.

---

## Overview

The goal is to update `atlas_db.csv` with `ref:hmdb`, `hmdb:Latitude`, `hmdb:Longitude`, `isHMDB`, and `memorial:website` values sourced from an HMDB bulk export. `ref:US-TX:thc` is the joining key between the two datasets.

---

## Step 1 — Obtain a fresh HMDB export

Download the Texas entries CSV from hmdb.org. The file will be named something like:

```
HMdb-Entries-in-Texas-YYYYMMDD.csv
```

Columns in this raw file: `MarkerID`, `Marker No.`, `Title`, `Subtitle`, `Add'l Subtitle`, `Year Erected`, `Erected By`, `Latitude (minus=S)`, `Longitude (minus=W)`, `Street Address`, `City or Town`, `Section or Quarter`, `County or Parish`, `State or Prov.`, `Location`, `Missing`, `Link`, `First Published`, `Last Update`

---

## Step 2 — Convert to OSM column format → `test.csv`

Use the built-in `convertHMDB` command to reformat the raw export into OSM-compatible column names:

```bash
thc convertHMDB --input HMdb-Entries-in-Texas-YYYYMMDD.csv --output test.csv
```

The resulting `test.csv` will have columns including: `ref:hmdb`, `ref:US-TX:thc`, `name`, `ErectedBy`, `hmdb:Latitude`, `hmdb:Longitude`, `addr:city`, `addr:county`, `isMissing`.

---

## Step 3 — Filter by `ErectedBy`

HMDB contains markers from many organisations. We only want official Texas state historical markers. Run the filter script to remove non-THC rows:

```bash
.venv/bin/python _filter_erected_by.py
```

This keeps rows where `ErectedBy` contains any of:
- `texas historical commission`
- `state historical survey committee`
- `texas state historical survey committee`
- `texas historical survey committee`
- `historical survey committee`
- `state of texas`

With explicit exclusions for:
- `state of texas highway department`
- `state of texas, board of control`

Co-sponsored entries (e.g. "Texas Historical Commission and the Moody Foundation", "Daughters of the American Revolution and The State of Texas") are **kept** because they still represent official THC markers.

Expected result: ~12,600–13,000 rows retained from ~17,000.

---

## Step 4 — Deduplicate `ref:US-TX:thc` in `test.csv`

Several HMDB entries share the same THC marker number due to:

- **Kings Highway / Camino Real trail markers** — a series that reuses low integer THC numbers (1–123 range) as placeholders. These are not real THC IDs.
- **True HMDB duplicates** — the same marker entered twice in HMDB.
- **Companion markers** — two related plaques sharing one THC number (e.g. husband/wife memorials).

Run the deduplication script, which resolves each conflict by keeping the test row whose name best matches the corresponding row in `atlas_db.csv` (the "known good"):

```bash
.venv/bin/python _dedup_test.py
```

For THC IDs where **no** test row name matches the atlas (e.g. Kings Highway rows with fake THC numbers), **all** rows for that ID are dropped.

Expected result: 0 duplicate `ref:US-TX:thc` keys remaining.

---

## Step 5 — Deduplicate `atlas_db.csv` (if needed)

Run the comparison script (Step 6). If it reports duplicate keys in `atlas_db.csv`, fix them first:

```bash
.venv/bin/python - << 'EOF'
import pandas as pd
atlas = pd.read_csv('atlas_db.csv', dtype=str, low_memory=False)
atlas['ref:US-TX:thc'] = atlas['ref:US-TX:thc'].str.strip()
# Only deduplicate rows that have a non-empty THC key
has_key = atlas['ref:US-TX:thc'].notna() & atlas['ref:US-TX:thc'].ne('')
dup_mask = has_key & atlas['ref:US-TX:thc'].duplicated(keep='first')
print(f"Dropping {dup_mask.sum()} duplicate rows")
atlas[~dup_mask].to_csv('atlas_db.csv', index=False)
EOF
```

Do **not** use `drop_duplicates()` without a mask — it will incorrectly collapse all rows with blank THC keys into one.

---

## Step 6 — Run the comparison and generate the report

```bash
.venv/bin/python _compare_report.py
```

This script:
1. Validates uniqueness of `ref:US-TX:thc` in both files — stops if duplicates found
2. Matches each test row to atlas by `ref:US-TX:thc`
3. Validates names (secondary check — allows case, whitespace, punctuation, parenthetical, and ~80% token-overlap differences)
4. Classifies each match into one of four outcomes (see below)
5. Prints a full report; **makes no changes**

### Outcome categories

| Category | File produced | Action |
|---|---|---|
| Unmatched (no THC ID in atlas) | — | Skipped; these are markers not yet in atlas |
| Name mismatch | `review_name_mismatches.csv` | Manual review |
| Proposed update (atlas missing HMDB) | `review_proposed_updates.csv` | Apply after review |
| HMDB conflict (atlas & test differ) | `review_hmdb_conflicts.csv` | Manual review |
| Already matching | — | No action needed |

---

## Step 7 — Review output files

Three CSV files are written to the working directory for review:

### `review_name_mismatches.csv`
Rows where the name in test.csv and atlas_db.csv differ enough to block automatic matching. Columns: `ref:US-TX:thc`, `test_name`, `atlas_name`, `test_ref:hmdb`, `atlas_ref:hmdb`, `addr:county`, `addr:city`.

Common causes: one file has "The …" prefix, subtitle differences, minor rewording. Many can be resolved by relaxing the name-matching threshold; others represent genuinely different markers with a shared THC number.

### `review_proposed_updates.csv`
Rows where atlas is missing `ref:hmdb` and test has it. Columns: `ref:US-TX:thc`, `name`, `new_ref:hmdb`, `new_hmdb:Latitude`, `new_hmdb:Longitude`, `new_isHMDB`, `new_memorial:website`, `addr:county`, `addr:city`.

Typically 1,000+ rows on a fresh sync. Spot-check a sample before applying.

### `review_hmdb_conflicts.csv`
Rows where both atlas and test have a `ref:hmdb` value but they differ. Columns: `ref:US-TX:thc`, `name`, `atlas_ref:hmdb`, `test_ref:hmdb`, `atlas_hmdb:url`, `test_hmdb:url`, `addr:county`, `addr:city`.

Both HMDB URLs are included for quick verification. **The test file (sourced from a fresh HMDB export) is typically correct** — the atlas value may be stale or mis-entered.

---

## Step 8 — Apply HMDB conflict corrections

Once confirmed that the test values are correct:

```bash
.venv/bin/python _apply_hmdb_conflicts.py
```

Updates `ref:hmdb`, `hmdb:Latitude`, `hmdb:Longitude`, `isHMDB`, and `memorial:website` in atlas for all rows in `review_hmdb_conflicts.csv`.

---

## Step 9 — Apply proposed updates

After reviewing `review_proposed_updates.csv`:

```bash
.venv/bin/python _apply_proposed_updates.py
```

Applies the same five fields (`ref:hmdb`, `hmdb:Latitude`, `hmdb:Longitude`, `isHMDB=True`, `memorial:website`) for all rows where atlas was previously missing a HMDB ID.

---

## Scripts reference

| Script | Purpose |
|---|---|
| `_filter_erected_by.py` | Step 3 — filter test.csv to THC-only rows |
| `_dedup_test.py` | Step 4 — resolve duplicate THC keys using atlas as ground truth |
| `_compare_report.py` | Step 6 — full comparison, produces review CSVs, no writes |
| `_apply_hmdb_conflicts.py` | Step 8 — apply conflict corrections to atlas_db.csv |
| `_apply_proposed_updates.py` | Step 9 — apply new HMDB additions to atlas_db.csv |

---

## Notes

- **Never use `drop_duplicates()` without a key mask on atlas_db.csv** — rows with blank `ref:US-TX:thc` will be incorrectly collapsed.
- The `_compare_report.py` script is read-only and safe to re-run at any time.
- Review files (`review_*.csv`) are overwritten on each run of `_compare_report.py`.
- `atlas_db.csv` is not tracked in git at time of writing — consider committing after a successful sync.

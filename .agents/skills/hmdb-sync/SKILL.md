---
name: hmdb-sync
description: Reconcile an hmdb.org marker export into atlas_db.csv. Use whenever the user supplies an hmdb-format CSV (single county, multi-county, city slice, or full Texas) and wants to enrich the canonical atlas with field-visitor data — ref:hmdb, hmdb coordinates, addr fields, Marker Notes, memorial:website, isHMDB, isMissing. Two-phase workflow with a mandatory human review step between identify and write.
---

# HMDB → atlas_db sync

Two-phase enrichment of `atlas_db.csv` from any hmdb.org export. Phase 1
auto-applies exact-name matches straight to atlas (no review needed) and
writes review CSVs for everything else. Phase 2 writes to atlas only the
rows the human dispositions as `YES`.

The Python lives in `pythonLib/thc_toolkit/hmdb_sync.py` and is wired into the
unified CLI as `thc hmdb reconcile` and `thc hmdb apply`. See
[references/strategy.md](references/strategy.md) for the design rationale.

## Read first

Read [references/strategy.md](references/strategy.md) before running. It
explains the filter rules, classification table, fuzzy thresholds, and the
ten enrichment-field mapping.

## Phase 1 — reconcile (auto-apply exact matches + write review CSVs)

```bash
thc hmdb reconcile <hmdb.csv> [--atlas atlas_db.csv] [--out-dir .] [--no-backup]
```

What it does:

1. Filter source rows whose `Erected By` fuzzily matches a THC canonical
   phrase (`Texas Historical Commission`, `Texas State Historical Survey
   Committee`, `State Historical Survey Committee`, `State of Texas`).
   Token-set ratio ≥ 0.85 with explicit drops for "State of Texas Highway
   Department" and "State of Texas, Board of Control".
2. Keep only rows whose `Marker No.` already appears as a `ref:US-TX:thc`
   in atlas. atlas_db is canonical — rows it doesn't know are out of scope.
3. Classify each surviving row by the atlas row's current `ref:hmdb`:
   already-equal → skip silently; populated-but-different → conflict file;
   empty → candidate.
4. For candidates, fuzzy-match `Title` vs atlas `name` (normalized: lower,
   punctuation stripped, leading `The ` dropped). Bucket by score:
   `score == 1.0` → **auto-apply** straight to atlas (covers "The X" vs
   "X" because of the normalization); `0.85 ≤ score < 1.0` →
   `review_candidates.csv`; `score < 0.85` → `review_name_mismatches.csv`.

Four CSVs land in `--out-dir`:

| file                           | meaning                                          |
|--------------------------------|--------------------------------------------------|
| `auto_applied.csv`             | exact-name matches already written to atlas      |
| `review_candidates.csv`        | name match passed but < 1.0; expected = approve  |
| `review_name_mismatches.csv`   | name match failed; needs human eyes              |
| `review_hmdb_conflicts.csv`    | atlas already carries a different `ref:hmdb`     |

When `auto_applied.csv` is non-empty, atlas_db is rewritten and a
`atlas_db.csv.bak.<ts>` backup is written first (suppressed by
`--no-backup`). Review rows have an `approve` column the human fills in
`YES` / `NO` (any text starting with `YES`, case-insensitive, counts as
approved).

## Phase 2 — apply (writes to atlas)

```bash
thc hmdb apply --hmdb <hmdb.csv> --review-dir <dir> [--atlas atlas_db.csv] [--no-backup]
```

What it does:

1. Read `review_candidates.csv` and `review_name_mismatches.csv` from
   `--review-dir`; collect every row whose `approve` starts with `YES`.
   (Conflicts file is intentionally **not** auto-applied — those need
   manual atlas edits.)
2. Look up each approved THC ID in the original hmdb CSV.
3. Write a timestamped backup `atlas_db.csv.bak.YYYYMMDD_HHMMSS` unless
   `--no-backup`.
4. Strict-overwrite the ten enrichment fields on every matched atlas row:

   | atlas field          | source                                            |
   |----------------------|---------------------------------------------------|
   | `ref:hmdb`           | hmdb `MarkerID`                                   |
   | `memorial:website`   | hmdb `Link`                                       |
   | `isHMDB`             | `True`                                            |
   | `isMissing`          | `True` iff hmdb `Missing` is Reported/Confirmed   |
   | `isPending`          | `False` (an hmdb ID means the marker is installed)|
   | `addr:full`          | hmdb `Street Address`                             |
   | `addr:city`          | hmdb `City or Town`                               |
   | `hmdb:Latitude`      | hmdb `Latitude (minus=S)`                         |
   | `hmdb:Longitude`     | hmdb `Longitude (minus=W)`                        |
   | `Marker Notes`       | `""` (erased — hmdb Location is not preserved)    |

   Strict overwrite means existing curated atlas values in these ten
   fields are replaced (user's standing decision: hmdb is more trustworthy
   than the THC-sourced free-text fields).

## Worked example (Tarrant)

```bash
# Phase 1
thc hmdb reconcile scripts/tarrant.csv \
    --atlas atlas_db.csv \
    --out-dir /tmp/hmdb_review_tarrant

# Human opens the three CSVs in a spreadsheet, sets approve = YES / NO

# Phase 2
thc hmdb apply --hmdb scripts/tarrant.csv \
    --review-dir /tmp/hmdb_review_tarrant \
    --atlas atlas_db.csv
```

## Guardrails

- Phase 1 only touches `atlas_db.csv` for rows whose name normalizes
  identically (`name_similarity == 1.0`). A backup is written first
  unless `--no-backup` is set, and only when there is at least one
  auto-apply row.
- Phase 2 always backs up first unless `--no-backup` is set.
- Conflicts (`review_hmdb_conflicts.csv`) require human resolution in
  `atlas_db.csv` directly — they are not auto-applied even if approved.
- The CSV writer pins `lineterminator="\n"` to preserve atlas's LF endings
  (Python's csv module defaults to CRLF, which caused a 17k-line spurious
  diff during early testing).
- The legacy multi-step pipeline in `pythonLib/_filter_erected_by.py`,
  `_dedup_test.py`, `_apply_hmdb_conflicts.py`, `_apply_proposed_updates.py`
  and `HMDB_sync_workflow.md` is superseded by this skill and will be
  removed once the new flow is fully trusted. Do not run both pipelines on
  the same atlas.

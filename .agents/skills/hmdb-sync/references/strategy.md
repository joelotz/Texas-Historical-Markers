# hmdb.org → atlas_db enrichment strategy

Workflow for taking a county (or all-Texas) export from hmdb.org and
enriching `atlas_db.csv` with the hmdb information field visitors have
added. atlas_db is the canonical universe of THC markers we care about;
this pass never adds new markers to atlas_db, it only fills hmdb-side
fields onto matching rows that already exist there.

The pass is identification → human review → write. Writes are paused
until the identification logic is debugged and the user gives the go.

## Inputs

- **Source CSV** (e.g. `scripts/tarrant.csv`): rows exported from
  hmdb.org. Relevant columns: `MarkerID`, `Marker No.`, `Title`,
  `Erected By`, `Latitude (minus=S)`, `Longitude (minus=W)`,
  `Street Address`, `City or Town`, `Location`, `Missing`, `Link`.
- **Target**: `atlas_db.csv`. Join keys:
  - `Marker No.` (hmdb) ↔ `ref:US-TX:thc` (atlas) — authoritative THC
    index, gates whether a row is in scope at all.
  - `MarkerID` (hmdb)  ↔ `ref:hmdb` (atlas) — hmdb page id, the field
    being filled in.

## Step 1 — filter source rows to "official THC marker" candidates

THC's institutional name has shifted over time and `Erected By` is
hand-typed, so straight equality won't do.

Accept a row only if `Erected By` fuzzily matches any of these canonical
phrases (token-set ratio ≥ ~85, case-insensitive, after stripping
punctuation):

- `Texas Historical Commission`
- `Texas State Historical Survey Committee`
- `State Historical Survey Committee`
- `State of Texas`

Compound entries like `Texas Historical Commission and North Fort Worth
Historical Society` are accepted because the THC phrase still appears.

Reject everything else (Heritage Trails, City of \*, Texas Rangers
Baseball Hall of Fame, Tarrant County Historical Society, etc.). A row
that fails this filter is out, period — no number-based rescue.

## Step 2 — restrict to rows whose THC number is in atlas

For each row that passed Step 1, look up `Marker No.` in the atlas
`ref:US-TX:thc` index.

- **No match** → out of scope (the marker is not in atlas_db at all).
  Discard silently. atlas_db is canonical; if a THC marker is missing
  from it, that's a separate problem fixed elsewhere.
- **Match** → this row is the considered set.

## Step 3 — split the considered set by hmdb-id state

For each considered row, inspect the matched atlas row's `ref:hmdb`:

| atlas `ref:hmdb` | tarrant `MarkerID` | class |
|------------------|--------------------|-------|
| populated, equal to tarrant `MarkerID` | — | **already documented** — skip silently |
| populated, ≠ tarrant `MarkerID`        | — | **conflict** — surface for human review, do nothing |
| empty                                  | populated | **candidate for enrichment** — go to Step 4 |

## Step 4 — title/name fuzzy match gate

For each candidate from Step 3, compare hmdb `Title` against atlas
`name` on the matched row using a normalized SequenceMatcher ratio
(case-insensitive, drop leading `The`, strip punctuation).

- Ratio == 1.0 → **auto-apply** — the normalized titles are identical
  (covers "The Henderson Depot" vs "Henderson Depot", "Mt. Zion" vs
  "Mt Zion", and similar). Write straight to atlas with no human
  review; the THC# match + identical normalized name is enough.
- 0.85 ≤ ratio < 1.0 → **confirmed candidate** — surface for review
  and (after approval) enrich.
- Below 0.85 → **name mismatch** — surface for human review with
  both strings shown; do nothing automatically.

## Step 5 — write review CSVs and auto-apply

Identification produces four CSV files in the chosen output directory.
Each row carries enough atlas-vs-hmdb context for the human to decide,
plus an `approve` column the human fills in `Y` / `N` before any
write step runs (already filled `YES (auto)` on the auto-apply file
for audit purposes).

| file                          | contents                                                          |
|-------------------------------|-------------------------------------------------------------------|
| `auto_applied.csv`            | Step 4 ratio == 1.0 — already written to atlas, kept as audit.    |
| `review_candidates.csv`       | Step 4 ratio in [0.85, 1.0) — needs eyes but expected to approve. |
| `review_name_mismatches.csv`  | Step 4 fails — title vs name diverged enough to need eyes.        |
| `review_hmdb_conflicts.csv`   | Step 3 conflicts — atlas already carries a different `ref:hmdb`.  |

Common columns: `ref:US-TX:thc` (= hmdb `Marker No.`), hmdb
`MarkerID`, hmdb `Title`, atlas `name`, hmdb `Erected By`, hmdb
`City or Town`, atlas `addr:city`, hmdb `County or Parish`, atlas
`addr:county`, hmdb `Missing`, hmdb `Link`, name-similarity score,
`approve`. The conflicts file additionally shows the atlas's existing
`ref:hmdb` so the human can pick a side.

`auto_applied.csv` is purely a log of what reconcile already wrote.
The other three are inputs to Phase 2 (`thc hmdb apply`). All four are
overwritten on every reconcile run.

When `auto_applied.csv` is non-empty, atlas_db is rewritten and a
timestamped `atlas_db.csv.bak.<ts>` is taken first (suppressed by
`--no-backup`).

## Step 6 — write (auto for exact matches in Step 5; otherwise apply phase)

For each auto-applied or human-approved candidate, update the matched
atlas row in place:

| atlas field          | source                                     |
|----------------------|--------------------------------------------|
| `ref:hmdb`           | tarrant `MarkerID`                         |
| `memorial:website`   | tarrant `Link`                             |
| `isHMDB`             | `True`                                     |
| `isMissing`          | `True` iff tarrant `Missing` ∈ {Reported Missing, Confirmed Missing} |
| `isPending`          | `False` — an hmdb ID means the marker is installed on the ground |
| `addr:full`          | tarrant `Street Address`                   |
| `addr:city`          | tarrant `City or Town`                     |
| `hmdb:Latitude`      | tarrant `Latitude (minus=S)`               |
| `hmdb:Longitude`     | tarrant `Longitude (minus=W)`              |
| `Marker Notes`       | `""` — erased on update; hmdb `Location` is reachable through `memorial:website` |

Strict overwrite is intentional: hmdb is treated as more trustworthy than
the THC-sourced free-text fields for the columns listed above.

Writes are live. Reconcile auto-applies the Step 4 ratio == 1.0 set
during Phase 1; everything else waits on human approval in Phase 2.

## Tarrant baseline (pre-implementation snapshot)

Running Step 1 alone on `scripts/tarrant.csv`: 502 rows in, ~324 pass
the THC fuzzy filter. Of those, ~315 also pass Step 2 (Marker No.
present in atlas). Of those, ~24 currently have an empty `ref:hmdb`
in atlas — those are the rows that will hit Step 4 for the title
gate. Exact counts will come out of the first script run.

## Scope and migration plan

Tarrant is a test bed. The script accepts any hmdb-format export — a
single county, several counties, a city slice, or the full Texas
file — as long as it has the raw hmdb columns (`MarkerID`,
`Marker No.`, `Title`, `Erected By`, `Latitude (minus=S)`,
`Longitude (minus=W)`, `Street Address`, `City or Town`, `Location`,
`Missing`, `Link`, `County or Parish`).

Once this version is trusted, the older multi-step pipeline in
`pythonLib/` (`_filter_erected_by.py`, `_dedup_test.py`, the
never-written `_compare_report.py`, `_apply_hmdb_conflicts.py`,
`_apply_proposed_updates.py`, and `HMDB_sync_workflow.md`) is to be
retired and removed in favor of this one. Don't touch those files
until the user gives the word.

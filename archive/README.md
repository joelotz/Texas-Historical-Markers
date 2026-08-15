# archive/

Recovery artifacts — data removed from `atlas_db.csv` that exists nowhere else.
Nothing here is read by the toolkit; these files exist so a decision can be
undone later.

## `thc_coordinates_before_20260814.csv`

The THC atlas coordinates that were overwritten on 2026-08-14, one row per
marker, 2,522 rows.

**Why it exists.** On 2026-08-14 a bulk pass rewrote `estimated:` coordinates
for 2,522 markers using roadhistorical.app, recording the previous value in each
row's `DATA_NOTE` as `original THC value was <lat>,<lon>`. On 2026-08-15
roadhistorical.app turned out to be a mirror of the THC atlas rather than an
independent source, so those notes claimed a verification that had not happened
and were removed. The removal would have destroyed the only record of the
pre-2026-08-14 coordinates, so they were extracted here first, with the values
lifted out of the note prose into their own columns.

| column | meaning |
|---|---|
| `ref:US-TX:thc`, `ref:hmdb`, `name` | identifies the marker |
| `original_thc_latitude` / `_longitude` | the THC value **before** 2026-08-14; empty where the marker had no coordinate at all (419 rows) |
| `current_estimated_latitude` / `_longitude` | what `atlas_db.csv` holds now |
| `current_verified_latitude` / `_longitude` | field-verified position, if one exists |
| `other_note_text` | any `DATA_NOTE` content that was **not** the roadhistorical sentence, preserved so nothing was lost silently (71 rows) |

**Should the coordinates be reverted?** Not obviously. Both the original and the
current value are THC-derived, so neither is more trustworthy than the other —
the current one is not *wrong*, it is just not independently verified as the
note claimed. Where a row now has a `verified:` coordinate, neither matters.
This file is here so the choice stays available, not because a revert is
pending.

Regenerating it is not possible: the source notes are gone from `atlas_db.csv`
as of commit `1651f9c`.

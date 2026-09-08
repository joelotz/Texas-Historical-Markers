---
name: hmdb-update
description: The whole "hmdb data update" cycle for atlas_db.csv and OSM in one runbook - pull the fresh hmdb.org Texas export, report everything that changed (new links, re-catalogued ids, missing flips, dead refs, hmdb-only markers) as a plan table for Joe, then on approval write the atlas, retag existing OSM nodes, create nodes for the newly linked rows, and rebuild SQLite. Use whenever Joe asks for an hmdb update / hmdb sync / "what's new on hmdb" / pull the latest hmdb data. Never writes before Joe has seen the plan.
---

# hmdb data update — end to end

One request ("update from hmdb", "pull the latest hmdb data and show me
what's new") → this runbook. Two gates: Joe sees the **plan table** before
any write, and every OSM script dry-runs before `--apply`. Scripts live in
`.agents/skills/hmdb-update/scripts/`; lower-level mechanics are documented
in `hmdb-fetch` (download) and `hmdb-sync` (reconcile/apply rules).

Read [references/decisions.md](references/decisions.md) first — it holds
Joe's standing decisions for every case the report can surface, so most
of the plan needs no questions.

## Phase A — pull and report (no writes)

```bash
thc hmdb fetch                                   # data_files/HMdb-Entries-Texas-YYYYMMDD.csv, auto re-auth
python .agents/skills/hmdb-update/scripts/hmdb_update_report.py \
    data_files/HMdb-Entries-Texas-YYYYMMDD.csv   # --prev picks the newest older export by itself
```

The report (stdout + `scripts/tmp/hmdb_review_YYYYMMDD/report.md`) gives:

0. **working tree** — uncommitted atlas rows split into LibreOffice
   coordinate churn vs Joe's real edits (a Calc lock file is flagged).
1. **snapshot diff** — added/removed MarkerIDs and who each removed one
   belonged to.
2. **dead refs** — atlas `ref:hmdb` absent from the export, each tagged
   *re-catalogued → new id*, *not yet published* (Joe's own pending
   submission, probed live with the cookie), *post-pull id*, or *gone*.
3. **missing flips** on linked rows.
4. **reconcile output, annotated** — the scratch-copy run of
   `thc hmdb reconcile` (atlas untouched) with, per row: new-since-prev,
   isActive=False, duplicate thc# group, OSM node, hmdb↔atlas coordinate
   distance (`>2 km <<<`), both addresses.
5. **hmdb-only** — added THC-erected pages the atlas can't place by
   Marker No.: same-county fuzzy matches against un-linked rows (typo'd
   Marker No.) and the nearest atlas row (genuinely new marker).
6. **plan table** — `| Name | ref:thc | hmdb url | kind |`.

Present the table to Joe with the sections that need a decision
(anything the decisions file doesn't already settle), and the working
tree state. Stop there until he answers.

## Phase B — atlas writes (after approval)

Order matters; each step is a script in `scripts/tmp/` following the
dated pattern, all writing with `newline=''` + `lineterminator='\n'`.

1. **Churn restore** if section 0 showed churn:
   copy `references/templates/restore_lo_churn_20260906.py` to `scripts/tmp/`
   and set `KEEP` to the thc#s with real edits. Result must be
   `git diff --numstat` == the real-edit rows only.
2. **Reconcile for real** — auto-applies exact-name links:
   `cp -p atlas_db.csv scripts/tmp/atlas_db.csv.bak.<ts>_prereconcile`
   `thc hmdb reconcile <export> --atlas atlas_db.csv --out-dir scripts/tmp/hmdb_review_YYYYMMDD --no-backup`
   (`--no-backup` because its backup would land in the repo root.)
3. **Approve candidates** — set `approve` = `YES` / `NO <reason>` in
   `review_candidates.csv` + `review_name_mismatches.csv`, then
   `thc hmdb apply --hmdb <export> --review-dir scripts/tmp/hmdb_review_YYYYMMDD --atlas atlas_db.csv --no-backup`.
   Typo'd Marker No. rows (section 5 cross-maps) cannot go through
   `apply`; link them by MarkerID in the extras script.
4. **Extras script** (copy `references/templates/hmdb_update_extras_20260906.py`
   to `scripts/tmp/` and edit the decisions block): missing-flag flips + DATA_NOTE, DATA_NOTE on
   re-catalogues Joe applied by hand, finish hand-linked rows
   (addr:city / isPending / Marker Notes), new rows for hmdb-only
   markers, weebly→hmdb coordinate replacement notes
   (`references/templates/weebly_note_20260906.py` — reconcile's strict
   overwrite replaces a weebly `verified:*` coord silently).
5. `thc atlas validate` and `thc atlas check --hmdb <export>` — the only
   acceptable check failure is *not yet published* ids from section 2.

## Phase C — OSM (after approval; Joe's default is "update OSM")

```bash
# existing nodes: re-catalogued ids and newly linked rows that already have a node
python .agents/skills/hmdb-update/scripts/retag_nodes.py \
    --swap THC:OLD:NEW ... --link THC ...            # dry run, then --apply

# new nodes for every isHMDB & !isOSM & active & !missing & !pending row
.agents/skills/hmdb-update/scripts/fetch_plaque_extract.sh scripts/tmp/overpass_tx_plaques_YYYYMMDD.json
python .agents/skills/hmdb-update/scripts/push_new_nodes.py \
    --extract scripts/tmp/overpass_tx_plaques_YYYYMMDD.json [--adopt THC=NODE] --dry-run
python .agents/skills/hmdb-update/scripts/push_new_nodes.py --extract ... [--adopt ...]
```

`push_new_nodes.py` aborts on any offline dedup hit; read the hit. A
plaque node carrying the atlas Details URL in `website` but no ref is
*ours* → `--adopt THC=NODE` (modify, keep the mapper's tags and
position). Anything else → investigate before re-running. It also aborts
if a live Overpass query finds any ref about to be written; after an
interrupted run, re-run — the state file skips what was created.

Missing markers keep their OSM node whether Reported or Confirmed (Joe,
2026-09-06); only `isMissing` and the DATA_NOTE change.

## Phase D — finish

```bash
thc sqlite build --csv atlas_db.csv --sqlite atlas_db.sqlite && thc sqlite verify --csv atlas_db.csv --sqlite atlas_db.sqlite
git diff --numstat atlas_db.csv        # rows changed must equal what you can name
```

Report to Joe: counts (links, re-catalogues, flips, new rows, nodes
created/adopted/retagged with changeset ids), anything skipped and why,
the open questions. **Do not commit** unless asked; remind him the
working tree holds the update.

## Guardrails

- Never run `thc hmdb reconcile` against the real atlas before Joe has
  seen the report — it auto-applies. The report script uses a scratch copy.
- Section 0 churn must be restored *before* any write, or it is baked
  into the commit (happened 2026-09-05).
- All OSM writes: dry-run first, `bot=no`, comment ≤ 255, ≤ 15 nodes per
  changeset, live pre-state assert, `validate_ref_plan` on both ref tags,
  re-fetch and count after (`45/45`), then stamp the atlas.
- One extra fetch per day at most; `--check-auth` for auth tests.
- Overpass's main endpoint 504s regularly; every script falls back to
  `lz4.overpass-api.de` and `overpass.kumi.systems`.

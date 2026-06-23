---
name: thc-osm-sync
description: Execute THC-to-OSM synchronization workflows safely. Use when an agent needs to create nodes from atlas data, validate duplicates/IDs, push nodes to JOSM remote control, compare atlas vs GeoJSON extracts, and update `isOSM` flags with verification steps.
---

# THC OSM Sync

Use this skill for the atlas -> OSM workflow.

## Workflow order

1. Validate atlas input contract first.
2. Generate nodes from CSV. Use `--only-missing-osm` to scope to rows where
   `isHMDB=True` and `isOSM=False` (HMDB-sourced markers not yet in OSM).
3. Run the dedup pre-check with `--dedup-check` so each candidate is compared
   against existing OSM `memorial=plaque` nodes within ~100 ft (configurable)
   and fuzzy-matched on name. Matches are removed from the output and written
   to a skipped-for-review JSON file.
4. Optionally push nodes to JOSM only when remote control is enabled.
5. **Human review in JOSM, then Upload from JOSM to OSM.** `push-josm` only
   stages nodes locally; the real OSM IDs do not exist until you click Upload.
6. After upload propagates, run `sync-from-osm` to query Overpass by
   `ref:US-TX:thc` for each node in `nodes.json` and stamp the atlas with
   `isOSM=True` AND `OsmNodeID=<id>`. Refs not yet visible (still in JOSM, or
   not yet propagated) are left untouched — re-run later.
7. (Legacy) `update-isOSM` blindly flips `isOSM=True` from `nodes.json`
   without querying OSM and does not populate `OsmNodeID`. Prefer
   `sync-from-osm` going forward.
8. (Optional) Compare atlas with a downloaded OSM extract via `find-missing`.
9. Re-run verification after code changes.

## Read first

Read [references/workflow.md](references/workflow.md).

## Scripted helpers

- Use `scripts/preflight.sh` for quick environment and input checks.
- Use `scripts/run_sync_example.sh` for a repeatable local dry-run flow.

## Guardrails

- Do not push to JOSM unless explicitly requested.
- Fail fast on duplicate IDs or invalid coordinate rows.
- Keep generated output paths explicit and reviewable.
- When `--dedup-check` is on, always inspect the skipped-for-review report
  before pushing — Overpass matches are advisory, not authoritative.
- Be polite to public Overpass: keep `--dedup-rate-limit-sec` at >= 1.0 unless
  using a private endpoint.

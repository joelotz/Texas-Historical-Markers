---
name: thc-osm-sync
description: Execute THC-to-OSM synchronization workflows safely. Use when an agent needs to create nodes from atlas data, validate duplicates/IDs, push nodes to JOSM remote control, compare atlas vs GeoJSON extracts, and update `isOSM` flags with verification steps.
---

# THC OSM Sync

Use this skill for the atlas -> OSM workflow.

## Workflow order

1. Validate atlas input contract first.
2. Generate nodes from CSV.
3. Optionally push nodes to JOSM only when remote control is enabled.
4. Compare atlas with OSM extract.
5. Update `isOSM` flags and write output CSV.
6. Re-run verification after code changes.

## Read first

Read [references/workflow.md](references/workflow.md).

## Scripted helpers

- Use `scripts/preflight.sh` for quick environment and input checks.
- Use `scripts/run_sync_example.sh` for a repeatable local dry-run flow.

## Guardrails

- Do not push to JOSM unless explicitly requested.
- Fail fast on duplicate IDs or invalid coordinate rows.
- Keep generated output paths explicit and reviewable.

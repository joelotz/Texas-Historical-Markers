# AGENTS.md

## What `thc_toolkit` Is For

`thc_toolkit` is a Python CLI/library for working with Texas Historical Commission (THC) marker datasets. It supports:

- Exporting and filtering marker CSV data (especially unmapped markers)
- Route and area mapping workflows (HTML map + CSV/GeoJSON/KML outputs)
- OSM/JOSM synchronization helpers (node creation, push, and atlas flag updates)
- HMDB-to-THC CSV conversion and related data prep utilities

## Canonical Entrypoints

Primary CLI entrypoint (packaged):

- `thc` (maps to `thc_toolkit.cli:main`)

Canonical subcommands:

- `thc counties`
- `thc route`
- `thc map`
- `thc viewcsv`
- `thc convertHMDB`
- `thc docs`

Module CLIs for direct development/debugging are also valid:

- `python -m thc_toolkit.cli`
- `python -m thc_toolkit.counties_cli`
- `python -m thc_toolkit.route_cli`
- `python -m thc_toolkit.map_cli`
- `python -m thc_toolkit.osm_cli`

## Code Organization Preferences

- Keep CLI argument parsing in `*_cli.py` modules; keep reusable logic in shared helpers (`utils.py` or focused helper modules).
- Prefer small, pure functions for data transforms; keep side effects (file/network/webbrowser) near command boundaries.
- Keep default paths and output naming consistent across CLI help text, docs, and implementation.
- Avoid duplicating business logic between subcommands; share common filtering/export helpers.
- Preserve backward compatibility of command flags and output schemas unless a deliberate versioned change is planned.

## Skills

Project-specific skills live under `.agents/skills/`. Each skill is a self-contained
folder with a `SKILL.md` (purpose + workflow), optional `references/` (deep context),
and optional `scripts/` (helpers). They are written in agent-neutral language so any
AI coding assistant can use them.

| Skill | When to use |
|-------|-------------|
| [`hmdb-sync`](.agents/skills/hmdb-sync/SKILL.md) | Reconcile an hmdb.org marker export into `atlas_db.csv`. Two-phase: identify → human review → apply. |
| [`thc-cli`](.agents/skills/thc-cli/SKILL.md) | Install, run, and verify the `thc` CLI; canonical subcommands and fallback invocations. |
| [`thc-data-quality`](.agents/skills/thc-data-quality/SKILL.md) | Audit CSV handling for NaNs, type coercion, duplicate IDs, silent corruption. |
| [`thc-osm-sync`](.agents/skills/thc-osm-sync/SKILL.md) | Atlas → OSM workflow: create nodes, push to JOSM, compare against extracts, update `isOSM`. |
| [`unmapped-markers-kml`](.agents/skills/unmapped-markers-kml/SKILL.md) | County tooling for markers without a `ref:hmdb`. Build mode generates a Google My Maps-ready KML (geocodes missing coords via Nominatim, flags `isPending`). Audit mode batch-geocodes addresses against the US Census Geocoder and flags rows where the stored `thc:Latitude`/`thc:Longitude` disagrees with the address by more than 0.5 mi. |

**Before acting** in any of these areas, read the relevant `SKILL.md` first — they
encode invariants (e.g. the hmdb-sync human-review gate, the data contract for
`atlas_db.csv`) that aren't obvious from the code alone.

### Layout

- **`.agents/skills/<name>/`** — the canonical, version-controlled location.
- **`.claude/skills/<name>/`** — relative symlinks into `.agents/skills/`, local-only
  (gitignored). They exist so Claude Code's discovery mechanism finds the skills.
  Other harnesses can be supported the same way by symlinking from their expected path.

This keeps a single source of truth in the repo while letting each contributor's
harness discover skills via the path it expects.

### Adding a skill

1. Create `.agents/skills/<name>/SKILL.md` with frontmatter (`name`, `description`).
2. Write the body in agent-neutral language — no harness-specific tool names,
   no `~/.claude/...` paths, no slash-command invocation instructions.
3. Add a row to the table above.
4. If the skill should be discoverable by your local agent, symlink it from the
   harness's expected directory (e.g. `ln -sfn ../../.agents/skills/<name> .claude/skills/<name>`).

## Python Version Target

- Target: Python `>=3.10`

## Preferred Invocation

- For end users and docs, prefer `thc ...` (installed console script).
- For local dev/debug in an editable checkout, `python -m thc_toolkit.cli ...` is acceptable.

## Tests, Lint, and Sample Commands

Run from `pythonLib/` unless otherwise noted.

### Install

```bash
cd pythonLib
pip install -e .
```

### Tests

```bash
cd pythonLib
pytest -q
```

Canonical verification command:

```bash
cd pythonLib
make verify
```

### Lint

No mandatory linter is currently wired in repo config. If `ruff` is available locally, use:

```bash
cd pythonLib
ruff check .
```

If `ruff` is not installed, document that lint was not run.

### Sample Commands

```bash
cd pythonLib
thc --help
thc counties --input ../atlas_db.csv --output ../scripts/UnmappedMarkersPerCounty --stats
thc route --track ../scripts/test.kml --data ../atlas_db.csv --radius 5 --csv
thc map --data ../atlas_db.csv --county Travis --unmapped --csv
python -m thc_toolkit.osm_cli --help
```

System tool note:

- `thc viewcsv` pretty mode uses `column` and `less`; if absent it falls back to raw output.

## Project Rules

- Do not change CLI behavior without updating:
  - CLI `--help` text
  - `pythonLib/README.md` usage examples
  - any relevant workflow docs
- Do not rename/remove flags or alter output columns/file naming without explicit documentation updates.
- Confirm with tests before claiming success.
- If no automated test covers a change, add/update tests or clearly state the gap and provide manual verification steps.
- Keep docs and code in sync: examples in docs should run as written.

## Command: `/review`

When the user issues the `/review` command, execute the following workflow autonomously:
1. **Tests**: Run all tests (e.g., `make verify` or `pytest`). If they fail, proactively fix the tests or code and try again.
2. **Lint**: Once tests pass, run the linter and formatter (e.g., `ruff format .` and `ruff check .`). Fix any linter errors iteratively until clean.
3. **Build**: Verify the build succeeds (e.g., `make verify`). Fix any issues and try again.
4. **Commit & Push**: After a passing review where tests, lint, and build all completely succeed, automatically group the changes into a git commit with a message summarizing what was modified, and `git push` to the remote repository.

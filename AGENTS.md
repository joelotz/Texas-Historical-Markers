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

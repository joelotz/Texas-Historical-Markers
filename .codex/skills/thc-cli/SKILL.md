---
name: thc-cli
description: Run and validate the Texas Historical Markers CLI reliably. Use when an agent needs to install the pythonLib package, execute canonical thc subcommands, run verification, or choose between `thc ...` and `python -m thc_toolkit.cli ...` while keeping docs/help/output behavior in sync.
---

# THC CLI

Use this skill for routine project command execution.

## Follow this order

1. Use repository root as working baseline.
2. Enter `pythonLib/` for CLI and test commands.
3. Prefer `thc ...` when available.
4. Fall back to `python -m thc_toolkit.cli ...` if `thc` is unavailable.
5. Run verification before claiming completion.

## Canonical commands

Read [references/commands.md](references/commands.md) for the exact command set.

## Fast path scripts

- Use `scripts/run_thc.sh` to run any `thc` subcommand with automatic fallback.
- Use `scripts/verify.sh` to run the verification suite in a consistent way.

## Guardrails

- Update CLI help text and `pythonLib/README.md` when behavior/flags/output naming change.
- Do not claim success without running tests (`make verify` or `pytest -q`).
- Keep outputs and flag behavior backward-compatible unless explicitly requested.

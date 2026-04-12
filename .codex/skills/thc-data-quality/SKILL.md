---
name: thc-data-quality
description: Audit and harden THC CSV handling and matching behavior. Use when an agent must check NaNs, missing columns, type mismatches, string normalization, duplicate IDs, and silent data corruption risks in filtering/export logic and tests.
---

# THC Data Quality

Use this skill for correctness-focused data and CLI audits.

## Review workflow

1. Inspect affected command module(s): `counties_cli.py`, `map_cli.py`, `route_cli.py`, `osm_cli.py`, `utils.py`.
2. Confirm required columns are validated before use.
3. Confirm boolean/int parsing does not silently coerce bad values.
4. Confirm matching uses shared normalization logic.
5. Confirm duplicate IDs are checked where data is exported, merged, or synced.
6. Add or update tests in `pythonLib/tests/` for every behavior change.
7. Run verification before reporting success.

## Data contract reference

Read [references/data-contract.md](references/data-contract.md) before edits.

## Utility script

Use `scripts/check_atlas_contract.py` for a quick contract pass on a CSV.

## Guardrails

- Prioritize correctness and explicit failure over silent coercion.
- Report confirmed defects separately from potential risk.
- Do not change CLI behavior without updating docs/help/tests.

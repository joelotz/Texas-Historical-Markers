# THC Data Contract

## Canonical ID fields

- `ref:US-TX:thc`
- `ref:hmdb`
- `OsmNodeID`

Rules:

- Treat ID columns as nullable integers.
- Reject invalid non-numeric non-empty values.
- Detect duplicate IDs before merge/export/sync.

## Boolean flags

Common boolean columns:

- `isMissing`
- `isPrivate`
- `isOSM`

Rules:

- Parse common bool tokens (`true/false`, `1/0`, `yes/no`, `y/n`, `t/f`).
- Reject unknown tokens.
- Avoid implicit truthiness from raw strings.

## Null and unmapped tokens

Common null-like tokens:

- `""`, `nan`, `none`, `null`, `na`, `<na>`

Unmapped HMDB logic should handle all null-like forms consistently.

## Matching normalization

For county/city/name matching:

- Strip whitespace.
- Apply case-insensitive compare via `casefold()`.
- Normalize Unicode and fold diacritics when needed.

## Test requirements

Changes in parsing/filtering/matching must include regression tests for:

- NaNs and null-like strings
- Missing required columns
- Type mismatch failures
- Duplicate ID handling
- Silent-failure prevention paths

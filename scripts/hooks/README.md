# Git hooks

Tracked hooks (currently just `pre-commit`) that guard the repo from
recurring accidents. Git hooks live under `.git/hooks/` which is not
tracked, so we ship the real files here and symlink from `.git/hooks/`.

## Install

```bash
scripts/hooks/install.sh
```

Idempotent; safe to re-run. Symlinks `.git/hooks/<name>` →
`../../scripts/hooks/<name>`.

## What each hook does

### `pre-commit`

Runs `thc atlas validate` when `atlas_db.csv` is staged. Fails the commit
if the file isn't UTF-8 clean or has CRLF line endings.

**Why:** LibreOffice Calc defaults to opening CSVs as ISO-8859-1
(cp1252). If you open `atlas_db.csv` with that setting and save it, every
multi-byte UTF-8 sequence in the file (any accented character, curly
quote, en-dash, etc.) gets rewritten as mojibake at the byte level.
Because CSV has no encoding marker, git can't tell that the "same"
17,000-row file is actually corrupted. This hook catches it before the
commit lands.

**When it fails:** re-encode via

    thc atlas repair --path atlas_db.csv

Which decodes each line as UTF-8, falls back to cp1252 → latin-1 for
lines that need it, and rewrites the file as canonical UTF-8/LF. Writes
a `.preencoding.bak.<ts>` sidecar and a report of which lines needed a
fallback so you can spot-check.

**Prevention going forward:** when opening `atlas_db.csv` in LibreOffice,
in the Text Import dialog set **Character set = "Unicode (UTF-8)"**. On
save, click "Use Text CSV Format" → "Edit filter settings" → confirm
UTF-8 and LF.

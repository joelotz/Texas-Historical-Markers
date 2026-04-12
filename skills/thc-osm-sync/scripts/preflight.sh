#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

if [[ ! -f atlas_db.csv ]]; then
  echo "[FAIL] atlas_db.csv not found at repo root"
  exit 1
fi

cd pythonLib
if command -v thc >/dev/null 2>&1; then
  thc --help >/dev/null
else
  python -m thc_toolkit.cli --help >/dev/null
fi

echo "[OK] preflight checks passed"

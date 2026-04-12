#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root/pythonLib"

python_bin="${PYTHON_BIN:-../.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="${PYTHON:-python}"
fi

PYTHON="$python_bin" make verify

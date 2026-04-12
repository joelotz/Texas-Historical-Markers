#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "Usage: run_thc.sh <thc args...>"
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root/pythonLib"

if command -v thc >/dev/null 2>&1; then
  thc "$@"
else
  python -m thc_toolkit.cli "$@"
fi

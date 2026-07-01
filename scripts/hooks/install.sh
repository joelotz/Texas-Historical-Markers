#!/usr/bin/env bash
# Install (or refresh) the tracked git hooks into .git/hooks/.
# Idempotent; safe to re-run.

set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

for hook in pre-commit; do
    src="$HOOKS_SRC/$hook"
    dst="$HOOKS_DST/$hook"
    if [[ ! -e "$src" ]]; then
        echo "  [SKIP] $hook (source $src missing)"
        continue
    fi
    ln -sf "../../scripts/hooks/$hook" "$dst"
    chmod +x "$src"
    echo "  [OK]   $hook → $(readlink "$dst")"
done

echo "hooks installed under $HOOKS_DST"

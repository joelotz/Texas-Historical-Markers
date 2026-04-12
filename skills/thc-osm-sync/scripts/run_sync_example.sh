#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root/pythonLib"

atlas="../atlas_db.csv"
out_nodes="/tmp/thc_nodes.json"
out_updated="/tmp/thc_updated_atlas.csv"

python -m thc_toolkit.osm_cli create-nodes --csv "$atlas" --out "$out_nodes"
python -m thc_toolkit.osm_cli update-isOSM --csv "$atlas" --nodes "$out_nodes" --out "$out_updated"

echo "[OK] wrote $out_nodes"
echo "[OK] wrote $out_updated"

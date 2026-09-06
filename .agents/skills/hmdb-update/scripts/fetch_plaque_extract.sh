#!/usr/bin/env bash
# One-shot statewide extract of memorial=plaque nodes for offline dedup (bbox = Texas).
# Usage: fetch_plaque_extract.sh OUT.json   -- tries three Overpass endpoints; validates JSON.
set -u
OUT="${1:?usage: fetch_plaque_extract.sh OUT.json}"
Q='[out:json][timeout:180][bbox:25.8,-106.7,36.6,-93.4];node["memorial"="plaque"];out;'
for EP in https://overpass-api.de/api/interpreter https://lz4.overpass-api.de/api/interpreter https://overpass.kumi.systems/api/interpreter; do
  curl -s -A "thc-toolkit/0.1 (joelotz@gmail.com)" --data-urlencode "data=$Q" "$EP" -o "$OUT"
  if python3 -c "import json,sys; d=json.load(open('$OUT')); print('plaque nodes:', len(d['elements']), 'osm_base:', d.get('osm3s',{}).get('timestamp_osm_base'), 'from $EP')" 2>/dev/null; then
    exit 0
  fi
  echo "failed: $EP" >&2; sleep 5
done
echo "all Overpass endpoints failed" >&2; exit 1

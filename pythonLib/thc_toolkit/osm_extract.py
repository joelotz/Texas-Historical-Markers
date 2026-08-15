"""The canonical statewide `memorial=plaque` extract.

This lived only in throwaway `scripts/tmp/*/pull.py` copies until 2026-08-15, and
each copy carried the same two blind spots forward:

* **Nodes only.** Nine TX features tagged `memorial=plaque` are ways, two of them
  with a `ref:US-TX:thc`. Because the query never saw them, a marker already
  mapped on a building footprint (thc#2333 Halff House) was imported a second time
  as a node without any dedup pass noticing.

* **`area["ISO3166-2"="US-TX"]` drops boundary markers.** A node sitting exactly on
  the state line is not inside the area: thc#13056 International Boundary Marker
  (TX/LA), thc#14559 Olivet Cemetery and thc#5274 Texas Territorial Compromise
  (both TX/NM). All three are alive and correctly tagged, yet every audit built on
  the area query reported them as missing from OSM.

A bounding box with a margin fixes the second; `out center` on ways fixes the
first while still yielding one representative coordinate per feature.

The `memorial=plaque` filter stays deliberately broad — narrowing it to
`historic=memorial` as well would miss the under-tagged duplicates that dedup
exists to find.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_USER_AGENT = (
    "thc-toolkit/0.1 (joelotz@gmail.com) TX historical marker reconciliation")

# Texas plus a margin wide enough to keep markers sitting on the state line.
TX_BBOX = (25.5, -107.0, 36.8, -93.3)   # south, west, north, east


def build_query(bbox: tuple[float, float, float, float] = TX_BBOX,
                timeout: int = 300, include_ways: bool = True) -> str:
    """Overpass QL for every memorial=plaque feature in the bbox."""
    s, w, n, e = bbox
    box = f"{s},{w},{n},{e}"
    parts = [f'node["memorial"="plaque"]({box});']
    if include_ways:
        parts.append(f'way["memorial"="plaque"]({box});')
    return (f"[out:json][timeout:{timeout}];"
            "(" + "".join(parts) + ");"
            "out tags center;")


def fetch(bbox: tuple[float, float, float, float] = TX_BBOX,
          endpoint: str = DEFAULT_ENDPOINT,
          user_agent: str = DEFAULT_USER_AGENT,
          include_ways: bool = True,
          timeout: int = 300,
          session: requests.Session | None = None) -> dict:
    http = session or requests
    r = http.post(endpoint,
                  data={"data": build_query(bbox, timeout, include_ways)},
                  timeout=timeout + 60, headers={"User-Agent": user_agent})
    r.raise_for_status()
    return r.json()


def coord_of(element: dict) -> tuple[float, float] | None:
    """Position of a node, or the `out center` centroid of a way."""
    if element.get("type") == "node" and "lat" in element:
        return float(element["lat"]), float(element["lon"])
    c = element.get("center")
    if c:
        return float(c["lat"]), float(c["lon"])
    return None


def summarize(payload: dict) -> dict:
    els = payload.get("elements", [])
    by_type: dict[str, int] = {}
    for e in els:
        by_type[e.get("type", "?")] = by_type.get(e.get("type", "?"), 0) + 1
    thc = [e for e in els if (e.get("tags") or {}).get("ref:US-TX:thc")]
    return {
        "total": len(els),
        "by_type": by_type,
        "with_thc_ref": len(thc),
        "ways_with_thc_ref": sum(1 for e in thc if e.get("type") == "way"),
        "timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
    }


def run_extract(args) -> None:
    payload = fetch(include_ways=not args.nodes_only)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    info = summarize(payload)
    print(f"[OK] wrote {out}  ({info['total']:,} elements)")
    print(f"     by type            : {info['by_type']}")
    print(f"     carrying a THC ref : {info['with_thc_ref']:,}"
          f"  (ways: {info['ways_with_thc_ref']})")
    print(f"     base timestamp     : {info['timestamp']}")
    if info["ways_with_thc_ref"]:
        print("     note: a THC marker mapped as a way is a tagging error — "
              "memorial=plaque belongs on a node")

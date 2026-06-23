"""
Reconcile uploaded JOSM edits back into atlas_db.csv.

After a JOSM upload pushes new ``memorial=plaque`` nodes to OpenStreetMap,
each node receives a real OSM ID. This module queries Overpass by
``ref:US-TX:thc`` in batches and returns ``{ref: osm_id}`` so the atlas can
be stamped with ``isOSM=True`` and ``OsmNodeID=<id>``.
"""

from __future__ import annotations

import time
from typing import Iterable

import requests

from .osm_dedup import DEFAULT_OVERPASS_ENDPOINT, DEFAULT_USER_AGENT


def _normalize_refs(refs: Iterable) -> list[str]:
    """Filter to non-empty integer-valued refs, returned as strings."""
    out: list[str] = []
    for r in refs:
        if r is None:
            continue
        s = str(r).strip()
        if not s or s.lower() in {"nan", "none", "null", "<na>"}:
            continue
        try:
            out.append(str(int(float(s))))
        except (TypeError, ValueError):
            continue
    return out


def _build_query(refs_batch: list[str], timeout: int) -> str:
    pattern = "|".join(refs_batch)
    return (
        f"[out:json][timeout:{timeout}];"
        f'node["ref:US-TX:thc"~"^({pattern})$"];'
        "out;"
    )


def query_osm_nodes_by_thc_refs(
    refs: Iterable,
    batch_size: int = 50,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    timeout: float = 50.0,
    rate_limit_sec: float = 1.5,
    user_agent: str = DEFAULT_USER_AGENT,
    session: requests.Session | None = None,
    log=print,
) -> dict[str, int]:
    """Look up ``{ref:US-TX:thc -> osm_node_id}`` for the given refs via Overpass.

    Refs not present in OSM are simply absent from the result. When OSM
    contains multiple nodes for the same ``ref:US-TX:thc``, the first one
    seen wins and a warning is logged — the atlas can't safely commit to
    a single ID until the duplication is resolved upstream.
    """
    normalized = _normalize_refs(refs)
    if not normalized:
        return {}

    http = session or requests
    headers = {"User-Agent": user_agent}
    result: dict[str, int] = {}
    duplicates: dict[str, list[int]] = {}

    batches = [
        normalized[i : i + batch_size] for i in range(0, len(normalized), batch_size)
    ]
    for i, batch in enumerate(batches, start=1):
        query = _build_query(batch, timeout=int(timeout))
        response = http.post(
            endpoint, data={"data": query}, timeout=timeout + 5, headers=headers
        )
        response.raise_for_status()
        payload = response.json()
        for el in payload.get("elements", []):
            if el.get("type") != "node":
                continue
            tags = el.get("tags") or {}
            ref = tags.get("ref:US-TX:thc")
            if ref is None:
                continue
            ref_s = str(ref).strip()
            osm_id = int(el["id"])
            if ref_s in result and result[ref_s] != osm_id:
                duplicates.setdefault(ref_s, [result[ref_s]]).append(osm_id)
            else:
                result[ref_s] = osm_id

        if log:
            log(
                f"[INFO] sync batch {i}/{len(batches)}: queried {len(batch)} refs, "
                f"matched {sum(1 for r in batch if r in result)} so far"
            )
        if rate_limit_sec and i < len(batches):
            time.sleep(rate_limit_sec)

    if duplicates and log:
        for ref_s, ids in duplicates.items():
            log(
                f"[WARN] ref:US-TX:thc={ref_s} has multiple OSM nodes "
                f"({ids}); kept first ({result[ref_s]})"
            )

    return result

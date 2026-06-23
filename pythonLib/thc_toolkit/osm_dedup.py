"""
OSM duplicate detection for candidate Texas Historical Marker nodes.

Before pushing a new node to OpenStreetMap, query Overpass for existing
``memorial=plaque`` nodes within a small radius and fuzzy-match the name.
If a credible match is found, the candidate is skipped and recorded for
manual review instead of silently creating a duplicate.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

import requests


DEFAULT_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_USER_AGENT = (
    "thc-toolkit/0.2.3 (+https://github.com/joelotz/Texas-Historical-Markers)"
)
FEET_PER_METER = 3.28084
EARTH_RADIUS_M = 6_371_000.0


_PUNCT_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_name(value) -> str:
    """Lowercase, strip diacritics and punctuation, collapse whitespace.

    Returns "" for null/blank values so similarity comparisons short-circuit.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def name_similarity(a, b) -> float:
    """Return a 0..1 similarity score between two free-text names.

    Uses :class:`difflib.SequenceMatcher` on normalized forms. Empty inputs
    score 0.0 so missing names never count as a match.
    """
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def haversine_ft(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in feet between two WGS84 points."""
    return haversine_m(lat1, lon1, lat2, lon2) * FEET_PER_METER


@dataclass
class OverpassNode:
    osm_id: int
    lat: float
    lon: float
    tags: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.tags.get("name", "")


def query_overpass_memorials_near(
    lat: float,
    lon: float,
    radius_m: float,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    timeout: float = 25.0,
    session: requests.Session | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[OverpassNode]:
    """Fetch ``memorial=plaque`` nodes within ``radius_m`` of (lat, lon)."""
    query = (
        f"[out:json][timeout:{int(timeout)}];"
        f'node["memorial"="plaque"](around:{radius_m:.2f},{lat:.7f},{lon:.7f});'
        "out;"
    )
    http = session or requests
    headers = {"User-Agent": user_agent}
    response = http.post(
        endpoint, data={"data": query}, timeout=timeout + 5, headers=headers
    )
    response.raise_for_status()
    payload = response.json()
    nodes: list[OverpassNode] = []
    for el in payload.get("elements", []):
        if el.get("type") != "node":
            continue
        nodes.append(
            OverpassNode(
                osm_id=int(el["id"]),
                lat=float(el["lat"]),
                lon=float(el["lon"]),
                tags=dict(el.get("tags", {}) or {}),
            )
        )
    return nodes


def find_duplicate(
    candidate_lat: float,
    candidate_lon: float,
    candidate_name,
    radius_ft: float = 100.0,
    name_threshold: float = 0.80,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    timeout: float = 25.0,
    session: requests.Session | None = None,
    nearby_nodes: Iterable[OverpassNode] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict | None:
    """Return a match descriptor when a near-duplicate OSM node exists.

    ``nearby_nodes`` lets callers inject pre-fetched results (used by tests
    and by callers that want to batch Overpass requests). When not provided,
    Overpass is queried for ``memorial=plaque`` nodes around the candidate.
    """
    radius_m = radius_ft / FEET_PER_METER
    if nearby_nodes is None:
        nearby_nodes = query_overpass_memorials_near(
            candidate_lat,
            candidate_lon,
            radius_m=radius_m,
            endpoint=endpoint,
            timeout=timeout,
            session=session,
            user_agent=user_agent,
        )

    best: dict | None = None
    for node in nearby_nodes:
        similarity = name_similarity(candidate_name, node.name)
        if similarity < name_threshold:
            continue
        distance_ft = haversine_ft(candidate_lat, candidate_lon, node.lat, node.lon)
        if distance_ft > radius_ft:
            continue
        if best is None or similarity > best["name_similarity"]:
            best = {
                "osm_id": node.osm_id,
                "name": node.name,
                "lat": node.lat,
                "lon": node.lon,
                "distance_ft": round(distance_ft, 2),
                "name_similarity": round(similarity, 4),
                "tags": node.tags,
            }
    return best

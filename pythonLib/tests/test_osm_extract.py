"""The statewide extract query must not reintroduce either blind spot.

Both are real: nine TX features tagged memorial=plaque are ways (two carrying a
ref:US-TX:thc, one of which caused a duplicate import), and three markers sit
exactly on the state line where an ISO3166-2 area filter excludes them.
"""
import pytest

from thc_toolkit import osm_extract


def test_query_includes_ways_by_default():
    q = osm_extract.build_query()
    assert 'way["memorial"="plaque"]' in q
    assert 'node["memorial"="plaque"]' in q


def test_query_asks_for_way_centres():
    """Without `out center` a way has no usable coordinate."""
    assert "out tags center;" in osm_extract.build_query()


def test_query_uses_a_bbox_not_the_iso_area():
    """area["ISO3166-2"="US-TX"] excludes markers sitting on the state line."""
    q = osm_extract.build_query()
    assert "ISO3166-2" not in q
    assert "area" not in q


def test_bbox_contains_the_three_state_line_markers():
    """thc#13056 (TX/LA), thc#14559 and thc#5274 (TX/NM) are all real and mapped."""
    s, w, n, e = osm_extract.TX_BBOX
    for lat, lon in [(32.0, -94.043), (31.8, -103.044), (32.0, -103.133)]:
        assert s < lat < n and w < lon < e


def test_nodes_only_is_available_but_not_the_default():
    assert 'way["memorial"="plaque"]' not in osm_extract.build_query(include_ways=False)


def test_filter_stays_broad_enough_for_dedup():
    """Narrowing to historic=memorial too would miss under-tagged duplicates."""
    assert "historic" not in osm_extract.build_query()


def test_coord_of_reads_nodes_and_way_centres():
    assert osm_extract.coord_of({"type": "node", "lat": "30.5", "lon": "-97.5"}) == (30.5, -97.5)
    assert osm_extract.coord_of(
        {"type": "way", "center": {"lat": "29.42", "lon": "-98.48"}}) == (29.42, -98.48)
    assert osm_extract.coord_of({"type": "way"}) is None


def test_summarize_counts_ways_carrying_a_thc_ref():
    payload = {"elements": [
        {"type": "node", "id": 1, "tags": {"ref:US-TX:thc": "1"}},
        {"type": "way", "id": 2, "tags": {"ref:US-TX:thc": "2333"}},
        {"type": "way", "id": 3, "tags": {}},
    ], "osm3s": {"timestamp_osm_base": "2026-08-15T19:41:51Z"}}
    info = osm_extract.summarize(payload)
    assert info["total"] == 3
    assert info["by_type"] == {"node": 1, "way": 2}
    assert info["with_thc_ref"] == 2
    assert info["ways_with_thc_ref"] == 1


def test_fetch_posts_the_query_and_returns_json():
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"elements": []}

    captured = {}

    class FakeSession:
        def post(self, endpoint, data, timeout, headers):
            captured["endpoint"] = endpoint
            captured["query"] = data["data"]
            captured["ua"] = headers["User-Agent"]
            return FakeResponse()

    out = osm_extract.fetch(session=FakeSession())
    assert out == {"elements": []}
    assert 'way["memorial"="plaque"]' in captured["query"]
    assert "joelotz" in captured["ua"]

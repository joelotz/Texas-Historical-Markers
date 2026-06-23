import json
import pytest
from unittest.mock import MagicMock, patch

from thc_toolkit import osm_cli, osm_dedup


class TestNormalizeAndSimilarity:
    def test_normalize_lowercases_and_strips_punct(self):
        assert (
            osm_dedup.normalize_name("  The O'Reilly–Smith Marker! ")
            == "the o reilly smith marker"
        )

    def test_normalize_handles_none_and_blank(self):
        assert osm_dedup.normalize_name(None) == ""
        assert osm_dedup.normalize_name("   ") == ""

    def test_normalize_folds_diacritics(self):
        assert osm_dedup.normalize_name("Bexár") == "bexar"

    def test_similarity_exact_match(self):
        assert osm_dedup.name_similarity("Fort Worth Marker", "Fort Worth Marker") == 1.0

    def test_similarity_near_match_above_threshold(self):
        score = osm_dedup.name_similarity(
            "Fort Worth Historical Marker", "Fort Worth Historic Marker"
        )
        assert score >= 0.80

    def test_similarity_empty_inputs_score_zero(self):
        assert osm_dedup.name_similarity("", "anything") == 0.0
        assert osm_dedup.name_similarity(None, None) == 0.0


class TestHaversine:
    def test_zero_distance(self):
        assert osm_dedup.haversine_ft(30.0, -97.0, 30.0, -97.0) == 0.0

    def test_about_100_feet_north(self):
        # ~100 ft north of a Texas lat: dlat ≈ 100 / 364000 deg
        dlat = 100.0 / 364000.0
        d = osm_dedup.haversine_ft(30.0, -97.0, 30.0 + dlat, -97.0)
        # tolerate small approximation
        assert 95.0 <= d <= 105.0


class TestFindDuplicate:
    def _node(self, osm_id, lat, lon, name):
        return osm_dedup.OverpassNode(
            osm_id=osm_id, lat=lat, lon=lon, tags={"memorial": "plaque", "name": name}
        )

    def test_returns_match_when_name_and_distance_qualify(self):
        nearby = [self._node(1, 30.0, -97.0, "Fort Worth Marker")]
        match = osm_dedup.find_duplicate(
            candidate_lat=30.0,
            candidate_lon=-97.0,
            candidate_name="Fort Worth Marker",
            radius_ft=100.0,
            name_threshold=0.80,
            nearby_nodes=nearby,
        )
        assert match is not None
        assert match["osm_id"] == 1
        assert match["name_similarity"] == 1.0
        assert match["distance_ft"] == 0.0

    def test_returns_none_when_name_below_threshold(self):
        nearby = [self._node(1, 30.0, -97.0, "Completely Different Plaque Title")]
        match = osm_dedup.find_duplicate(
            candidate_lat=30.0,
            candidate_lon=-97.0,
            candidate_name="Fort Worth Marker",
            radius_ft=100.0,
            name_threshold=0.80,
            nearby_nodes=nearby,
        )
        assert match is None

    def test_returns_none_when_outside_radius(self):
        # Far node ~ many miles north
        nearby = [self._node(1, 31.0, -97.0, "Fort Worth Marker")]
        match = osm_dedup.find_duplicate(
            candidate_lat=30.0,
            candidate_lon=-97.0,
            candidate_name="Fort Worth Marker",
            radius_ft=100.0,
            name_threshold=0.80,
            nearby_nodes=nearby,
        )
        assert match is None

    def test_picks_best_similarity_when_multiple_match(self):
        nearby = [
            self._node(1, 30.0, -97.0, "Fort Worth Historic Marker"),
            self._node(2, 30.0, -97.0, "Fort Worth Marker"),
        ]
        match = osm_dedup.find_duplicate(
            candidate_lat=30.0,
            candidate_lon=-97.0,
            candidate_name="Fort Worth Marker",
            radius_ft=100.0,
            name_threshold=0.80,
            nearby_nodes=nearby,
        )
        assert match is not None
        assert match["osm_id"] == 2


class TestOverpassQuery:
    def test_query_parses_overpass_response(self):
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {
            "elements": [
                {
                    "type": "node",
                    "id": 42,
                    "lat": 30.5,
                    "lon": -97.5,
                    "tags": {"memorial": "plaque", "name": "Test"},
                },
                {"type": "relation", "id": 99},  # ignored
            ]
        }
        session.post.return_value = response

        nodes = osm_dedup.query_overpass_memorials_near(
            30.0, -97.0, radius_m=30.0, session=session
        )

        assert len(nodes) == 1
        assert nodes[0].osm_id == 42
        assert nodes[0].name == "Test"
        # Verify Overpass query body contains the right operator + tag
        call = session.post.call_args
        body = call.kwargs["data"]["data"]
        assert 'node["memorial"="plaque"]' in body
        assert "around:30.00,30.0000000,-97.0000000" in body
        # Must use `out;` not `out tags;` so node coords are returned
        assert "out;" in body and "out tags;" not in body
        # Overpass blocks default python-requests UA; confirm we send a project UA
        assert call.kwargs["headers"]["User-Agent"].startswith("thc-toolkit/")


class TestApplyDedupCheckIntegration:
    def test_dedup_skips_duplicates_and_writes_report(self, tmp_path):
        nodes = [
            {
                "lat": 30.0,
                "lon": -97.0,
                "tags": {
                    "name": "Fort Worth Marker",
                    "memorial": "plaque",
                    "ref:US-TX:thc": 1001,
                    "ref:hmdb": 5001,
                },
            },
            {
                "lat": 31.0,
                "lon": -98.0,
                "tags": {
                    "name": "Brand New Marker",
                    "memorial": "plaque",
                    "ref:US-TX:thc": 1002,
                    "ref:hmdb": 5002,
                },
            },
        ]

        def fake_find_duplicate(
            candidate_lat, candidate_lon, candidate_name, **kwargs
        ):
            if candidate_name == "Fort Worth Marker":
                return {
                    "osm_id": 999,
                    "name": "Fort Worth Marker",
                    "lat": candidate_lat,
                    "lon": candidate_lon,
                    "distance_ft": 12.3,
                    "name_similarity": 1.0,
                    "tags": {"memorial": "plaque"},
                }
            return None

        with patch.object(osm_dedup, "find_duplicate", side_effect=fake_find_duplicate):
            kept, skipped = osm_cli._apply_dedup_check(
                nodes,
                radius_ft=100.0,
                name_threshold=0.80,
                rate_limit_sec=0,
                endpoint=osm_dedup.DEFAULT_OVERPASS_ENDPOINT,
            )

        assert [n["tags"]["ref:US-TX:thc"] for n in kept] == [1002]
        assert len(skipped) == 1
        assert skipped[0]["candidate"]["ref:US-TX:thc"] == 1001
        assert skipped[0]["match"]["osm_id"] == 999
        # JSON serializable
        json.dumps(skipped)

    def test_dedup_keeps_candidate_on_query_failure(self):
        nodes = [
            {
                "lat": 30.0,
                "lon": -97.0,
                "tags": {
                    "name": "Test Marker",
                    "memorial": "plaque",
                    "ref:US-TX:thc": 1001,
                    "ref:hmdb": 5001,
                },
            }
        ]

        with patch.object(
            osm_dedup, "find_duplicate", side_effect=RuntimeError("overpass down")
        ):
            kept, skipped = osm_cli._apply_dedup_check(
                nodes,
                radius_ft=100.0,
                name_threshold=0.80,
                rate_limit_sec=0,
                endpoint=osm_dedup.DEFAULT_OVERPASS_ENDPOINT,
            )

        assert len(kept) == 1
        assert skipped == []

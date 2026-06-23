import pandas as pd
import pytest
from unittest.mock import MagicMock

from thc_toolkit import osm_cli, osm_sync


class TestNormalizeRefs:
    def test_drops_null_tokens_and_blank(self):
        out = osm_sync._normalize_refs([None, "", "nan", "<NA>", " ", pd.NA])
        assert out == []

    def test_keeps_numeric_strings_and_ints(self):
        out = osm_sync._normalize_refs(["94", 219, "256.0", "  349  "])
        assert out == ["94", "219", "256", "349"]

    def test_rejects_garbage(self):
        out = osm_sync._normalize_refs(["abc", "12.x", "94"])
        assert out == ["94"]


class TestBuildQuery:
    def test_regex_pattern_wraps_refs(self):
        q = osm_sync._build_query(["94", "219", "256"], timeout=50)
        assert '[out:json][timeout:50]' in q
        assert 'node["ref:US-TX:thc"~"^(94|219|256)$"]' in q
        assert q.endswith("out;")


class TestQueryOsmNodesByThcRefs:
    def _session_returning(self, *payloads):
        session = MagicMock()
        responses = []
        for p in payloads:
            r = MagicMock()
            r.json.return_value = p
            responses.append(r)
        session.post.side_effect = responses
        return session

    def test_returns_ref_to_id_mapping_for_single_batch(self):
        session = self._session_returning(
            {
                "elements": [
                    {
                        "type": "node",
                        "id": 1001,
                        "lat": 32.0,
                        "lon": -97.0,
                        "tags": {"ref:US-TX:thc": "94"},
                    },
                    {
                        "type": "node",
                        "id": 1002,
                        "lat": 32.1,
                        "lon": -97.1,
                        "tags": {"ref:US-TX:thc": "219"},
                    },
                ]
            }
        )
        out = osm_sync.query_osm_nodes_by_thc_refs(
            ["94", "219", "256"],
            batch_size=50,
            rate_limit_sec=0,
            session=session,
            log=lambda *_: None,
        )
        assert out == {"94": 1001, "219": 1002}
        assert session.post.call_count == 1
        body = session.post.call_args.kwargs["data"]["data"]
        assert 'node["ref:US-TX:thc"~"^(94|219|256)$"]' in body
        assert session.post.call_args.kwargs["headers"]["User-Agent"].startswith(
            "thc-toolkit/"
        )

    def test_splits_into_batches(self):
        # Two batches of 2 refs each
        session = self._session_returning(
            {"elements": [{"type": "node", "id": 1, "lat": 0, "lon": 0,
                           "tags": {"ref:US-TX:thc": "94"}}]},
            {"elements": [{"type": "node", "id": 2, "lat": 0, "lon": 0,
                           "tags": {"ref:US-TX:thc": "349"}}]},
        )
        out = osm_sync.query_osm_nodes_by_thc_refs(
            ["94", "219", "349", "374"],
            batch_size=2,
            rate_limit_sec=0,
            session=session,
            log=lambda *_: None,
        )
        assert out == {"94": 1, "349": 2}
        assert session.post.call_count == 2

    def test_warns_on_ambiguous_ref_keeps_first(self):
        session = self._session_returning(
            {
                "elements": [
                    {"type": "node", "id": 10, "lat": 0, "lon": 0,
                     "tags": {"ref:US-TX:thc": "94"}},
                    {"type": "node", "id": 11, "lat": 0, "lon": 0,
                     "tags": {"ref:US-TX:thc": "94"}},
                ]
            }
        )
        logs = []
        out = osm_sync.query_osm_nodes_by_thc_refs(
            ["94"],
            batch_size=50,
            rate_limit_sec=0,
            session=session,
            log=logs.append,
        )
        assert out == {"94": 10}
        assert any("multiple OSM nodes" in m for m in logs)

    def test_empty_refs_short_circuits(self):
        session = MagicMock()
        out = osm_sync.query_osm_nodes_by_thc_refs(
            [None, "nan"], session=session, rate_limit_sec=0
        )
        assert out == {}
        session.post.assert_not_called()


class TestApplySyncResults:
    def _atlas(self):
        return pd.DataFrame(
            {
                "ref:US-TX:thc": pd.Series([94, 219, 256, 349], dtype="Int32"),
                "name": ["A", "B", "C", "D"],
                "isOSM": pd.Series(
                    [False, False, False, True], dtype="boolean"
                ),
                "OsmNodeID": pd.Series([pd.NA, pd.NA, pd.NA, 999], dtype="Int64"),
            }
        )

    def test_stamps_matched_refs(self):
        atlas = self._atlas()
        mapping = {"94": 1001, "219": 1002}
        updated, n, missing = osm_cli.apply_sync_results(atlas, mapping)
        assert n == 2
        assert missing == []
        assert bool(updated.loc[updated["ref:US-TX:thc"] == 94, "isOSM"].iloc[0])
        assert updated.loc[updated["ref:US-TX:thc"] == 94, "OsmNodeID"].iloc[0] == 1001
        assert updated.loc[updated["ref:US-TX:thc"] == 219, "OsmNodeID"].iloc[0] == 1002
        # Unmatched rows untouched
        assert not bool(updated.loc[updated["ref:US-TX:thc"] == 256, "isOSM"].iloc[0])
        assert pd.isna(updated.loc[updated["ref:US-TX:thc"] == 256, "OsmNodeID"].iloc[0])
        # Already-set row preserved
        assert updated.loc[updated["ref:US-TX:thc"] == 349, "OsmNodeID"].iloc[0] == 999

    def test_reports_refs_not_in_atlas(self):
        atlas = self._atlas()
        mapping = {"94": 1001, "9999": 2002}  # 9999 not in atlas
        _, n, missing = osm_cli.apply_sync_results(atlas, mapping)
        assert n == 1
        assert missing == [9999]

    def test_empty_mapping_noop(self):
        atlas = self._atlas()
        updated, n, missing = osm_cli.apply_sync_results(atlas, {})
        assert n == 0
        assert missing == []
        pd.testing.assert_frame_equal(updated, atlas)

    def test_missing_columns_raise(self):
        bad = pd.DataFrame({"ref:US-TX:thc": [94], "isOSM": [False]})
        with pytest.raises(ValueError, match="OsmNodeID"):
            osm_cli.apply_sync_results(bad, {"94": 1})

    def test_handles_float_osmnodeid_column(self):
        # Simulates a CSV read where OsmNodeID came in as float64 because of NaNs
        atlas = pd.DataFrame(
            {
                "ref:US-TX:thc": pd.Series([94, 219], dtype="Int32"),
                "isOSM": pd.Series([False, False], dtype="boolean"),
                "OsmNodeID": pd.Series([float("nan"), float("nan")], dtype="float64"),
            }
        )
        updated, n, _ = osm_cli.apply_sync_results(atlas, {"94": 1001})
        assert n == 1
        assert updated["OsmNodeID"].dtype.name == "Int64"
        assert updated.loc[updated["ref:US-TX:thc"] == 94, "OsmNodeID"].iloc[0] == 1001

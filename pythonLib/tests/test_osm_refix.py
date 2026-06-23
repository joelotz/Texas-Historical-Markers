import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from thc_toolkit import osm_refix


class TestLoadPlan:
    def test_requires_id_and_correct_ref(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("id,name\n123,foo\n")
        with pytest.raises(ValueError, match="correct_ref"):
            osm_refix.load_plan(p)

    def test_rejects_na_rows(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("id,correct_ref\n123,\n")
        with pytest.raises(ValueError, match="NA"):
            osm_refix.load_plan(p)

    def test_returns_int64_columns(self, tmp_path):
        p = tmp_path / "ok.csv"
        p.write_text("id,correct_ref,name\n123,7,foo\n456,8,bar\n")
        df = osm_refix.load_plan(p)
        assert str(df["id"].dtype) == "Int64"
        assert str(df["correct_ref"].dtype) == "Int64"


class TestState:
    def test_load_missing_returns_empty(self, tmp_path):
        s = osm_refix.load_state(tmp_path / "missing.json")
        assert s == {"pushed": {}}

    def test_save_and_load_roundtrip(self, tmp_path):
        p = tmp_path / "state.json"
        osm_refix.save_state(p, {"pushed": {"42": {"correct_ref": 7}}})
        s = osm_refix.load_state(p)
        assert s["pushed"]["42"]["correct_ref"] == 7

    def test_reset_state_clears_all(self, tmp_path):
        p = tmp_path / "state.json"
        osm_refix.save_state(p, {"pushed": {"1": {}, "2": {}}})
        n = osm_refix.reset_state(p)
        assert n == 2
        assert osm_refix.load_state(p) == {"pushed": {}}

    def test_reset_state_clears_specific_ids(self, tmp_path):
        p = tmp_path / "state.json"
        osm_refix.save_state(p, {"pushed": {"1": {}, "2": {}, "3": {}}})
        n = osm_refix.reset_state(p, ids=[2])
        assert n == 1
        assert set(osm_refix.load_state(p)["pushed"].keys()) == {"1", "3"}


class TestPushOne:
    def test_dry_run_makes_no_http_call(self):
        session = MagicMock()
        res = osm_refix.push_one(123, 7, session=session, dry_run=True)
        assert res.ok is True
        assert res.body == "<dry-run>"
        session.get.assert_not_called()

    def test_sends_load_object_with_addtags(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200, text="OK")
        res = osm_refix.push_one(
            123, 7, endpoint="http://example/", session=session,
        )
        assert res.ok is True
        url, kwargs = session.get.call_args.args[0], session.get.call_args.kwargs
        assert url == "http://example/load_object"
        assert kwargs["params"]["objects"] == "n123"
        assert kwargs["params"]["addtags"] == "ref:US-TX:thc=7"

    def test_non_200_marks_fail(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=400, text="no layer")
        res = osm_refix.push_one(123, 7, session=session)
        assert res.ok is False
        assert res.status == 400


class TestRunBatch:
    def _plan(self, n=5):
        return pd.DataFrame({
            "id": pd.array(range(1000, 1000 + n), dtype="Int64"),
            "correct_ref": pd.array(range(1, n + 1), dtype="Int64"),
        })

    def test_dry_run_does_not_write_state(self, tmp_path):
        state_path = tmp_path / "state.json"
        plan = self._plan(3)
        out = osm_refix.run_batch(
            plan, state_path=state_path, batch_size=10,
            rate_limit_sec=0, dry_run=True, log=lambda *_: None,
        )
        assert out["ok"] == 3
        assert out["fail"] == 0
        # State file should not exist or should be empty: dry-run is read-only
        assert not state_path.exists() or osm_refix.load_state(state_path) == {"pushed": {}}

    def test_resumes_skipping_already_pushed(self, tmp_path):
        state_path = tmp_path / "state.json"
        plan = self._plan(5)
        # mark first 2 as already pushed
        osm_refix.save_state(state_path, {"pushed": {"1000": {}, "1001": {}}})
        out = osm_refix.run_batch(
            plan, state_path=state_path, batch_size=2,
            rate_limit_sec=0, dry_run=True, log=lambda *_: None,
        )
        assert out["ok"] == 2
        assert out["pushed_ids"] == [1002, 1003]
        # 2 still pending (1004)
        assert out["pending_remaining"] == 1

    def test_empty_pending_returns_zero_work(self, tmp_path):
        state_path = tmp_path / "state.json"
        plan = self._plan(2)
        osm_refix.save_state(state_path, {"pushed": {"1000": {}, "1001": {}}})
        out = osm_refix.run_batch(
            plan, state_path=state_path, batch_size=10,
            rate_limit_sec=0, dry_run=True, log=lambda *_: None,
        )
        assert out["ok"] == 0
        assert out["pending_remaining"] == 0

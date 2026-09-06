"""The fetch CLI must re-login exactly once on an expired cookie, never on a
valid one, and must honour --no-auto-refresh / --refresh-auth / --check-auth."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from thc_toolkit import hmdb_fetch as hf


class _Log:
    def __init__(self, fail_first: int = 0):
        self.fail_first = fail_first
        self.verify_calls = 0
        self.refresh_calls = 0

    def make_session(self, cookie_path=None):
        return object()

    def verify(self, session):
        self.verify_calls += 1
        if self.verify_calls <= self.fail_first:
            raise hf.AuthExpired("expired")

    def refresh(self, display=None, timeout_s=180):
        self.refresh_calls += 1


def _args(tmp_path, **kw):
    cookie = tmp_path / "hmdb.session"
    cookie.write_text("HistoricalMarkerDB=SessionID={x}&UserID=1\n")
    base = dict(cookie=str(cookie), refresh_auth=False, no_auto_refresh=False, check_auth=False)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def wire(monkeypatch):
    def _wire(log: _Log):
        monkeypatch.setattr(hf, "make_session", log.make_session)
        monkeypatch.setattr(hf, "verify_session", log.verify)
        monkeypatch.setattr(hf, "refresh_auth", log.refresh)
        return log
    return _wire


def test_valid_cookie_never_refreshes(tmp_path, wire):
    log = wire(_Log())
    hf._authenticated_session(_args(tmp_path))
    assert (log.verify_calls, log.refresh_calls) == (1, 0)


def test_expired_cookie_refreshes_once_then_verifies(tmp_path, wire):
    log = wire(_Log(fail_first=1))
    hf._authenticated_session(_args(tmp_path))
    assert (log.verify_calls, log.refresh_calls) == (2, 1)


def test_no_auto_refresh_raises(tmp_path, wire):
    log = wire(_Log(fail_first=1))
    with pytest.raises(hf.AuthExpired):
        hf._authenticated_session(_args(tmp_path, no_auto_refresh=True))
    assert log.refresh_calls == 0


def test_forced_refresh_logs_in_before_verifying(tmp_path, wire):
    log = wire(_Log())
    hf._authenticated_session(_args(tmp_path, refresh_auth=True))
    assert (log.verify_calls, log.refresh_calls) == (1, 1)


def test_forced_refresh_does_not_loop_on_second_failure(tmp_path, wire):
    log = wire(_Log(fail_first=5))
    with pytest.raises(hf.AuthExpired):
        hf._authenticated_session(_args(tmp_path, refresh_auth=True))
    assert log.refresh_calls == 1


def test_missing_cookie_file_triggers_login(tmp_path, wire):
    log = wire(_Log())
    args = _args(tmp_path)
    args.cookie = str(tmp_path / "absent.session")
    hf._authenticated_session(args)
    assert log.refresh_calls == 1


def test_check_auth_skips_download(tmp_path, wire, monkeypatch):
    log = wire(_Log())
    monkeypatch.setattr(hf, "fetch_state_listing", lambda *a, **k: pytest.fail("must not download"))
    hf.run_fetch(_args(tmp_path, check_auth=True))
    assert log.verify_calls == 1


def test_add_auth_flags_defaults():
    import argparse
    ap = argparse.ArgumentParser()
    hf.add_auth_flags(ap)
    ns = ap.parse_args([])
    assert (ns.refresh_auth, ns.no_auto_refresh, ns.check_auth) == (False, False, False)
    assert ap.parse_args(["--check-auth", "--no-auto-refresh"]).check_auth is True

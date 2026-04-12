import argparse
import sys

from thc_toolkit import cli
from thc_toolkit import sqlite_sync


def test_main_dispatches_viewcsv_subcommand(monkeypatch):
    called = {}

    def fake_run_viewcsv(args):
        called["file"] = args.file
        called["head"] = args.head
        called["raw"] = args.raw

    monkeypatch.setattr(cli, "run_viewcsv", fake_run_viewcsv)
    monkeypatch.setattr(
        sys, "argv", ["thc", "viewcsv", "sample.csv", "--head", "1", "--raw"]
    )

    cli.main()

    assert called["file"] == "sample.csv"
    assert called["head"] == 1
    assert called["raw"] is True


def test_run_map_only_calls_map_cli(monkeypatch):
    called = {"map": False}

    def fake_run_with_args(args):
        called["map"] = True
        assert args.data == "atlas.csv"

    monkeypatch.setattr(cli.map_cli, "run_with_args", fake_run_with_args)

    args = argparse.Namespace(data="atlas.csv")
    cli.run_map(args)

    assert called["map"] is True


def test_main_dispatches_sqlite_build_subcommand(monkeypatch):
    called = {"build": False}

    def fake_build(
        csv_path,
        sqlite_path,
        table_name=sqlite_sync.DEFAULT_TABLE_NAME,
        strict_ids=False,
    ):
        called["build"] = True
        assert csv_path == "source.csv"
        assert sqlite_path == "target.sqlite"
        assert table_name == sqlite_sync.DEFAULT_TABLE_NAME
        assert strict_ids is False

    monkeypatch.setattr(sqlite_sync, "build_sqlite_from_csv", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        ["thc", "sqlite", "build", "--csv", "source.csv", "--sqlite", "target.sqlite"],
    )

    cli.main()

    assert called["build"] is True


def test_main_dispatches_sqlite_browse_subcommand(monkeypatch):
    called = {"browse": False}

    class FakeServer:
        def serve_forever(self):
            called["browse"] = True

        def server_close(self):
            return None

    def fake_serve(sqlite_path, table_name, host, port, open_browser):
        assert sqlite_path == "browser.sqlite"
        assert table_name == sqlite_sync.DEFAULT_TABLE_NAME
        assert host == "127.0.0.1"
        assert port == 8765
        assert open_browser is False
        return FakeServer()

    monkeypatch.setattr(cli.sqlite_viewer, "serve_sqlite_browser", fake_serve)
    monkeypatch.setattr(
        sys,
        "argv",
        ["thc", "sqlite", "browse", "--sqlite", "browser.sqlite", "--no-open"],
    )

    cli.main()

    assert called["browse"] is True

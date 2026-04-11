import argparse
import sys

from thc_toolkit import cli


def test_main_dispatches_viewcsv_subcommand(monkeypatch):
    called = {}

    def fake_run_viewcsv(args):
        called["file"] = args.file
        called["head"] = args.head
        called["raw"] = args.raw

    monkeypatch.setattr(cli, "run_viewcsv", fake_run_viewcsv)
    monkeypatch.setattr(sys, "argv", ["thc", "viewcsv", "sample.csv", "--head", "1", "--raw"])

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

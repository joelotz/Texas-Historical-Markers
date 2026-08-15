import pandas as pd
import pytest

from thc_toolkit.utils import resolve_coords


def _df(rows):
    return pd.DataFrame(rows, columns=[
        "verified:Latitude", "verified:Longitude",
        "estimated:Latitude", "estimated:Longitude",
    ])


def test_verified_wins_when_both_present():
    lat, lon = resolve_coords(_df([[30.5, -97.5, 31.9, -98.1]]))
    assert lat.iloc[0] == 30.5
    assert lon.iloc[0] == -97.5


def test_falls_back_to_estimated_when_verified_missing():
    lat, lon = resolve_coords(_df([[None, None, 31.9, -98.1]]))
    assert lat.iloc[0] == 31.9
    assert lon.iloc[0] == -98.1


def test_resolves_per_row_not_per_column():
    """A verified row and an estimate-only row in the same frame."""
    lat, lon = resolve_coords(_df([
        [30.5, -97.5, 31.9, -98.1],   # verified
        [None, None, 32.7, -96.8],    # estimate only
    ]))
    assert list(lat) == [30.5, 32.7]
    assert list(lon) == [-97.5, -96.8]


def test_all_na_when_neither_populated():
    lat, lon = resolve_coords(_df([[None, None, None, None]]))
    assert lat.isna().all() and lon.isna().all()


def test_non_numeric_values_become_na_not_errors():
    lat, lon = resolve_coords(_df([["", "", "not-a-number", "-98.1"]]))
    assert pd.isna(lat.iloc[0])


def test_works_with_only_the_verified_pair():
    df = pd.DataFrame([[30.5, -97.5]],
                      columns=["verified:Latitude", "verified:Longitude"])
    lat, lon = resolve_coords(df)
    assert lat.iloc[0] == 30.5


def test_works_with_only_the_estimated_pair():
    df = pd.DataFrame([[31.9, -98.1]],
                      columns=["estimated:Latitude", "estimated:Longitude"])
    lat, lon = resolve_coords(df)
    assert lat.iloc[0] == 31.9


def test_raises_when_no_coordinate_column_exists():
    with pytest.raises(ValueError, match="neither"):
        resolve_coords(pd.DataFrame([[1]], columns=["name"]), context="thing")


def test_real_atlas_prefers_verified(tmp_path):
    """Against the real atlas: every row holding a verified pair resolves to it."""
    from pathlib import Path
    atlas = Path(__file__).resolve().parents[2] / "atlas_db.csv"
    if not atlas.exists():
        pytest.skip("atlas_db.csv not present")
    df = pd.read_csv(atlas, low_memory=False)
    lat, lon = resolve_coords(df, context="atlas")

    vlat = pd.to_numeric(df["verified:Latitude"], errors="coerce")
    have = vlat.notna()
    assert have.sum() > 10_000, "expected most rows to carry a verified coord"
    assert (lat[have] == vlat[have]).all(), "verified coord was not preferred"

    # And rows with only an estimate fall back rather than dropping out.
    elat = pd.to_numeric(df["estimated:Latitude"], errors="coerce")
    est_only = elat.notna() & vlat.isna()
    assert est_only.sum() > 0
    assert (lat[est_only] == elat[est_only]).all()

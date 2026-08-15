import pandas as pd

from thc_toolkit.counties_cli import export_single_county
from thc_toolkit.map_cli import filter_markers
from thc_toolkit.utils import viewcsv_search


def test_export_single_county_matches_case_insensitive(tmp_path):
    df = pd.DataFrame(
        [
            {"addr:county": "Travis", "ref:US-TX:thc": 1001},
            {"addr:county": "Denton", "ref:US-TX:thc": 1002},
        ]
    )

    summary = export_single_county(df, "travis", str(tmp_path), simple=False)

    assert summary == {"travis": 1}


def test_export_single_county_matches_whitespace_and_diacritics(tmp_path):
    df = pd.DataFrame(
        [
            {"addr:county": " Bexár ", "ref:US-TX:thc": 1001},
            {"addr:county": "Denton", "ref:US-TX:thc": 1002},
        ]
    )

    summary = export_single_county(df, "bexar", str(tmp_path), simple=False)

    assert summary == {"bexar": 1}


def test_filter_markers_matches_county_city_case_and_whitespace():
    df = pd.DataFrame(
        [
            {
                "isMissing": False,
                "isOSM": False,
                "addr:county": "  Travis ",
                "addr:city": " AuStin  ",
                "verified:Latitude": pd.NA,
                "verified:Longitude": pd.NA,
                "estimated:Latitude": 30.2672,
                "estimated:Longitude": -97.7431,
            },
            {
                "isMissing": False,
                "isOSM": False,
                "addr:county": "Denton",
                "addr:city": "Denton",
                "verified:Latitude": 33.2148,
                "verified:Longitude": -97.1331,
                "estimated:Latitude": 33.2148,
                "estimated:Longitude": -97.1331,
            },
        ]
    )

    out = filter_markers(df, county="travis", city="austin")

    assert len(out) == 1
    assert out.iloc[0]["addr:county"].strip().lower() == "travis"
    assert out.iloc[0]["addr:city"].strip().lower() == "austin"


def test_filter_markers_unmapped_only_filters_isosm_true():
    df = pd.DataFrame(
        [
            {
                "isMissing": False,
                "isOSM": False,
                "addr:county": "Travis",
                "addr:city": "Austin",
                "verified:Latitude": 30.1,
                "verified:Longitude": -97.1,
                "estimated:Latitude": 30.1,
                "estimated:Longitude": -97.1,
            },
            {
                "isMissing": False,
                "isOSM": True,
                "addr:county": "Travis",
                "addr:city": "Austin",
                "verified:Latitude": 30.2,
                "verified:Longitude": -97.2,
                "estimated:Latitude": 30.2,
                "estimated:Longitude": -97.2,
            },
        ]
    )

    out = filter_markers(df, county="travis", city="austin", unmapped=True)

    assert len(out) == 1
    assert bool(out.iloc[0]["isOSM"]) is False


def test_filter_markers_normalizes_boolean_text_and_diacritics():
    df = pd.DataFrame(
        [
            {
                "isMissing": "false",
                "isOSM": "no",
                "addr:county": "Bexár",
                "addr:city": "San Antonio",
                "verified:Latitude": "29.4241",
                "verified:Longitude": "-98.4936",
                "estimated:Latitude": pd.NA,
                "estimated:Longitude": pd.NA,
            },
            {
                "isMissing": "false",
                "isOSM": "yes",
                "addr:county": "Bexar",
                "addr:city": "San Antonio",
                "verified:Latitude": "29.5",
                "verified:Longitude": "-98.5",
                "estimated:Latitude": pd.NA,
                "estimated:Longitude": pd.NA,
            },
        ]
    )

    out = filter_markers(df, county="bexar", city="san antonio", unmapped=True)
    assert len(out) == 1
    assert out.iloc[0]["addr:county"] == "Bexár"


def test_viewcsv_search_name_matching_case_insensitive_and_partial(tmp_path):
    csv_path = tmp_path / "names.csv"
    pd.DataFrame(
        [
            {"name": "Old Stone Church"},
            {"name": "STONEWALL MEMORIAL"},
            {"name": "River Ferry Marker"},
            {"name": pd.NA},
        ]
    ).to_csv(csv_path, index=False)

    out = viewcsv_search(str(csv_path), "stone")

    names = out["name"].tolist()
    assert len(out) == 2
    assert "Old Stone Church" in names
    assert "STONEWALL MEMORIAL" in names

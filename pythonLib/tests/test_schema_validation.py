import json
import pandas as pd
import pytest

from thc_toolkit import map_cli, route_cli, osm_cli


def test_map_filter_markers_missing_required_column_raises():
    df = pd.DataFrame([{"addr:county": "Travis"}])
    with pytest.raises(ValueError, match="missing required column\\(s\\): isMissing"):
        map_cli.filter_markers(df)


def test_route_require_columns_reports_missing():
    df = pd.DataFrame([{"ref:hmdb": 1, "thc:Latitude": 30.0}])
    with pytest.raises(
        ValueError, match="missing required column\\(s\\): thc:Longitude"
    ):
        route_cli.require_columns(
            df, ["ref:hmdb", "thc:Latitude", "thc:Longitude"], context="route input"
        )


def test_osm_find_missing_requires_ref_column(tmp_path):
    atlas = pd.DataFrame([{"name": "Marker"}])
    geo = tmp_path / "osm.geojson"
    geo.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    with pytest.raises(
        ValueError, match="missing required column\\(s\\): ref:US-TX:thc"
    ):
        osm_cli.find_missing_osm(atlas, str(geo))


def test_osm_find_missing_rejects_duplicate_geojson_refs(tmp_path):
    atlas = pd.DataFrame([{"ref:US-TX:thc": 1001}])
    geo = tmp_path / "osm_dupe.geojson"
    geo.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"ref:US-TX:thc": "1001"}},
                    {"type": "Feature", "properties": {"ref:US-TX:thc": "1001"}},
                ],
            }
        )
    )

    with pytest.raises(
        ValueError, match="geojson has duplicate values in ref:US-TX:thc"
    ):
        osm_cli.find_missing_osm(atlas, str(geo))


def test_route_unmapped_ref_series_treats_null_and_na_as_unmapped():
    series = pd.Series(["", "nan", "none", "null", "na", pd.NA, "5001"])
    out = route_cli._is_unmapped_ref_series(series)
    assert out.tolist() == [True, True, True, True, True, True, False]


def test_route_unmapped_ref_value_treats_scalar_na_and_tokens_as_unmapped():
    assert route_cli._is_unmapped_ref_value(pd.NA) is True
    assert route_cli._is_unmapped_ref_value(" <NA> ") is True
    assert route_cli._is_unmapped_ref_value("null") is True
    assert route_cli._is_unmapped_ref_value("5001") is False


def test_osm_create_nodes_invalid_coords_raise():
    df = pd.DataFrame(
        [
            {
                "name": "Marker",
                "ref:US-TX:thc": "1001",
                "ref:hmdb": "5001",
                "website": "https://example.com",
                "hmdb:Latitude": "bad-lat",
                "hmdb:Longitude": "-97.0",
            }
        ]
    )
    with pytest.raises(ValueError, match="create_nodes input has invalid rows"):
        osm_cli.create_nodes(df)

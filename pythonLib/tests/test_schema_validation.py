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
    with pytest.raises(ValueError, match="missing required column\\(s\\): thc:Longitude"):
        route_cli.require_columns(df, ["ref:hmdb", "thc:Latitude", "thc:Longitude"], context="route input")


def test_osm_find_missing_requires_ref_column(tmp_path):
    atlas = pd.DataFrame([{"name": "Marker"}])
    geo = tmp_path / "osm.geojson"
    geo.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    with pytest.raises(ValueError, match="missing required column\\(s\\): ref:US-TX:thc"):
        osm_cli.find_missing_osm(atlas, str(geo))

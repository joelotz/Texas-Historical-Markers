import pytest
import pandas as pd
import json
from unittest.mock import patch, MagicMock
from thc_toolkit.utils import (
    convert_hmdb_csv,
    create_nodes,
    push2josm,
    find_missing_osm,
    update_isOSM,
    viewcsv_pretty,
    require_columns,
)

class TestUtils:
    def test_require_columns_raises_for_missing(self):
        df = pd.DataFrame([{"a": 1}])
        with pytest.raises(ValueError, match="missing required column\\(s\\): b"):
            require_columns(df, ["a", "b"], context="test")

    def test_viewcsv_pretty_falls_back_when_tools_missing(self, monkeypatch, tmp_path):
        """If column/less are unavailable, pretty view should degrade to raw output."""
        csv_path = tmp_path / "tiny.csv"
        csv_path.write_text("name\nTest Marker\n")

        called = {"raw": False}

        def fake_which(_):
            return None

        def fake_viewcsv_raw(path, max_rows=200):
            called["raw"] = True
            assert str(path) == str(csv_path)

        monkeypatch.setattr("thc_toolkit.utils.shutil.which", fake_which)
        monkeypatch.setattr("thc_toolkit.utils.viewcsv_raw", fake_viewcsv_raw)

        viewcsv_pretty(str(csv_path))
        assert called["raw"] is True

    def test_convert_hmdb_csv_success(self, dummy_hmdb_csv, tmp_path):
        """Test converting HMDB format to internal OSM compliant format."""
        # Arrange
        output_file = str(tmp_path / "converted.csv")
        
        # Act
        df_result = convert_hmdb_csv(dummy_hmdb_csv, output_file)
        
        # Assert
        assert (tmp_path / "converted.csv").exists()
        assert "ref:hmdb" in df_result.columns
        assert "ref:US-TX:thc" in df_result.columns
        assert df_result.iloc[0]["ref:hmdb"] == "5001"
        assert df_result.iloc[0]["ref:US-TX:thc"] == "1001"
        assert "ExtraCol" not in df_result.columns

    def test_convert_hmdb_csv_missing_fields_raises_error(self, tmp_path):
        """Test that missing required columns raise a ValueError."""
        # Arrange
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("MarkerID,Title\n123,Test\n")
        output_file = str(tmp_path / "out.csv")
        
        # Act & Assert
        with pytest.raises(ValueError, match="Missing expected column"):
            convert_hmdb_csv(str(bad_csv), output_file)

    def test_convert_hmdb_csv_rejects_non_numeric_ref_values(self, tmp_path):
        bad = tmp_path / "hmdb_bad_ids.csv"
        bad.write_text(
            "MarkerID,Marker No.,Title,Erected By,Latitude (minus=S),Longitude (minus=W),"
            "Street Address,City or Town,County or Parish,Missing\n"
            "A5001,1001,Title A,State of Texas,30.1,-97.1,123 Main,Austin,Travis,False\n"
        )
        out = tmp_path / "out.csv"

        with pytest.raises(ValueError, match="Invalid non-numeric values in ref:hmdb"):
            convert_hmdb_csv(str(bad), str(out))

    def test_create_nodes_from_dataframe(self, sample_atlas_df):
        """Test converting a dataframe into OSM node dictionaries."""
        # Arrange is handled by the fixture
        
        # Act
        nodes = create_nodes(sample_atlas_df)
        
        # Assert
        # 3 rows in df, 3 nodes created
        assert len(nodes) == 3
        # Spot check node 0
        node = nodes[0]
        assert node["lat"] == 30.1
        assert node["lon"] == -97.1
        assert node["tags"]["name"] == "Marker A"
        assert node["tags"]["ref:US-TX:thc"] == 1001
        assert node["tags"]["memorial:website"] == "https://www.hmdb.org/m.asp?m=5001"
        assert node["tags"]["operator"] == "Texas Historical Commission"

    def test_create_nodes_missing_required_column_raises(self, sample_atlas_df):
        bad_df = sample_atlas_df.drop(columns=["website"])
        with pytest.raises(ValueError, match="missing required column\\(s\\): website"):
            create_nodes(bad_df)

    def test_create_nodes_allows_missing_start_date(self, sample_atlas_df):
        no_start = sample_atlas_df.drop(columns=["start_date"])
        nodes = create_nodes(no_start)
        assert len(nodes) == len(no_start)
        assert "start_date" not in nodes[0]["tags"]

    def test_create_nodes_output_is_json_serializable_with_missing_values(self, sample_atlas_df):
        nodes = create_nodes(sample_atlas_df)
        # Should not raise even when refs/coords/tags contain missing values.
        json.dumps(nodes)

    @patch("thc_toolkit.utils.requests.get")
    def test_push2josm_success(self, mock_get):
        """Test pushing nodes to JOSM with a successful network response."""
        # Arrange
        nodes = [
            {"lat": 30.0, "lon": -97.0, "tags": {"name": "Test", "ref:US-TX:thc": 9999}}
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Act
        added_refs = push2josm(nodes)
        
        # Assert
        mock_get.assert_called_once()
        # Verify the lat/lon/tags are passed correctly as params to the mock
        args, kwargs = mock_get.call_args
        assert kwargs["params"]["lat"] == 30.0
        assert kwargs["params"]["lon"] == -97.0
        assert "name=Test" in kwargs["params"]["addtags"]
        assert "ref:US-TX:thc=9999" in kwargs["params"]["addtags"]
        assert added_refs == [9999]

    @patch("thc_toolkit.utils.requests.get")
    def test_push2josm_omits_none_and_empty_tags(self, mock_get):
        nodes = [
            {
                "lat": 30.0,
                "lon": -97.0,
                "tags": {
                    "name": "Test",
                    "ref:US-TX:thc": 9999,
                    "ref:hmdb": None,
                    "source:website": "",
                },
            }
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        added_refs = push2josm(nodes)

        args, kwargs = mock_get.call_args
        addtags = kwargs["params"]["addtags"]
        assert "name=Test" in addtags
        assert "ref:US-TX:thc=9999" in addtags
        assert "ref:hmdb=None" not in addtags
        assert "source:website=" not in addtags
        assert added_refs == [9999]

    @patch("thc_toolkit.utils.requests.get")
    def test_push2josm_failure(self, mock_get):
        """Test pushing nodes handling a failed network response."""
        # Arrange
        nodes = [
            {"lat": 30.0, "lon": -97.0, "tags": {"name": "Test", "ref:US-TX:thc": 9999}}
        ]
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        # Act
        added_refs = push2josm(nodes)
        
        # Assert
        assert len(added_refs) == 0

    def test_find_missing_osm(self, sample_atlas_df, dummy_geojson_file):
        """Test finding THC refs that exist in atlas but not in the OSM geojson."""
        # Arrange
        # sample_atlas_df has THC refs: 1001, 1002, 1003
        # dummy_geojson_file has ref: 1001
        
        # Act
        missing = find_missing_osm(sample_atlas_df, dummy_geojson_file)
        
        # Assert
        assert missing == [1002, 1003]

    def test_update_isOSM(self, sample_atlas_df):
        """Test updating the isOSM flag natively."""
        # Arrange
        # sample_atlas_df starts with:
        # 1001 -> True, 1002 -> False, 1003 -> False
        refs_to_update = [1002]
        
        # Act
        updated_df = update_isOSM(refs_to_update, sample_atlas_df)
        
        # Assert
        # 1001 should still be True, 1002 should become True, 1003 should be False
        assert updated_df.loc[updated_df["ref:US-TX:thc"] == 1001, "isOSM"].iloc[0] == True
        assert updated_df.loc[updated_df["ref:US-TX:thc"] == 1002, "isOSM"].iloc[0] == True
        assert updated_df.loc[updated_df["ref:US-TX:thc"] == 1003, "isOSM"].iloc[0] == False

    def test_update_isOSM_missing_isOSM_column_raises(self, sample_atlas_df):
        bad_df = sample_atlas_df.drop(columns=["isOSM"])
        with pytest.raises(ValueError, match="missing required column\\(s\\): isOSM"):
            update_isOSM([1002], bad_df)

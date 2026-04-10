import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from thc_toolkit.utils import (
    convert_hmdb_csv,
    create_nodes,
    push2josm,
    find_missing_osm,
    update_isOSM
)

class TestUtils:

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


import pytest
import pandas as pd
import json
import os
from thc_toolkit.counties_cli import (
    load_filtered,
    enforce_integer_safe,
    apply_simple,
    export_single_county,
    export_counties,
    merge_all
)

class TestCountiesCLI:

    @pytest.fixture
    def dummy_counties_file(self, sample_atlas_df, tmp_path):
        """Writes the sample_atlas_df to a CSV and returns the path."""
        # sample_atlas_df has:
        # 1001 (Travis) - has ref:hmdb (5001) -> mapped
        # 1002 (Travis) - has ref:hmdb (5002) but isPrivate=True -> mapped & private
        # 1003 (Williamson) - no ref:hmdb, isMissing=True -> missing
        # Let's add an unmapped, public, not missing to ensure it passes load_filtered
        new_row = pd.DataFrame([{
            "ref:US-TX:thc": 1004,
            "ref:hmdb": pd.NA,
            "name": "Unmapped Target",
            "hmdb:Latitude": 30.5,
            "hmdb:Longitude": -97.5,
            "isOSM": False,
            "isMissing": False,
            "isPrivate": False,
            "addr:county": "Travis",
            "addr:city": "Austin"
        }])
        df = pd.concat([sample_atlas_df, new_row], ignore_index=True)
        file_path = str(tmp_path / "test_atlas.csv")
        df.to_csv(file_path, index=False)
        return file_path

    def test_load_filtered(self, dummy_counties_file):
        """Test that load_filtered correctly removes private, missing, and already-mapped markers."""
        # Arrange
        # 1001: mapped (has ref:hmdb)
        # 1002: mapped, isPrivate
        # 1003: missing
        # 1004: unmapped, public (should be kept)
        
        # Act
        df_filtered = load_filtered(dummy_counties_file)
        
        # Assert
        assert len(df_filtered) == 1
        assert int(df_filtered.iloc[0]["ref:US-TX:thc"]) == 1004

    def test_enforce_integer_safe(self, sample_atlas_df):
        """Test that enforcement corrects object/float types into Int64 safely."""
        # Arrange
        # Mess up datatypes
        sample_atlas_df["ref:US-TX:thc"] = sample_atlas_df["ref:US-TX:thc"].astype(float)
        # Act
        df_safe = enforce_integer_safe(sample_atlas_df)
        
        # Assert
        assert df_safe["ref:US-TX:thc"].dtype.name == "Int64"
        assert df_safe["ref:hmdb"].dtype.name == "Int64"
        assert df_safe["OsmNodeID"].dtype.name == "Int64"

    def test_apply_simple(self, sample_atlas_df):
        """Test that apply_simple trims the dataframe to required columns and enforces integers."""
        # Arrange
        # sample_atlas_df contains many columns, including some simple ones but missing OsmNodeID
        
        # Act
        df_simple = apply_simple(sample_atlas_df)
        
        # Assert
        expected_cols = [
            "ref:US-TX:thc", "ref:hmdb", "OsmNodeID", "name",
            "website", "memorial:website", "addr:city", "addr:county",
            "thc:Latitude", "thc:Longitude"
        ]
        assert list(df_simple.columns) == expected_cols
        assert pd.isna(df_simple.iloc[0]["OsmNodeID"])
        assert df_simple["OsmNodeID"].dtype.name == "Int64"
        assert df_simple["ref:US-TX:thc"].dtype.name == "Int64"

    def test_export_single_county(self, dummy_counties_file, tmp_path):
        """Test exporting a single county outputs the correct file and row counts."""
        # Arrange
        df = load_filtered(dummy_counties_file) # df only has 1 valid row (Travis 1004)
        outdir = str(tmp_path / "out")
        
        # Act
        summary = export_single_county(df, "Travis", outdir, simple=True)
        
        # Assert
        assert summary["Travis"] == 1
        outfile = tmp_path / "out" / "Travis.csv"
        assert outfile.exists()
        
        # Verify simple mode applied
        out_df = pd.read_csv(outfile)
        assert "OsmNodeID" in out_df.columns
        assert "isMissing" not in out_df.columns

    def test_export_counties_creates_files(self, dummy_counties_file, tmp_path):
        """Test that export_counties partitions by county correctly."""
        # Arrange
        df = pd.read_csv(dummy_counties_file) 
        # Using unfiltered df just to test partitioning logic
        # It has Travis and Williamson
        outdir = str(tmp_path / "out_all")
        
        # Act
        summary = export_counties(df, outdir)
        
        # Assert
        assert summary["Travis"] == 3
        assert summary["Williamson"] == 1
        assert (tmp_path / "out_all" / "Travis.csv").exists()
        assert (tmp_path / "out_all" / "Williamson.csv").exists()

    def test_merge_all(self, dummy_counties_file, tmp_path):
        """Test running a merge operation stores to single file."""
        # Arrange
        df = pd.read_csv(dummy_counties_file)
        merge_path = str(tmp_path / "merged.csv")
        
        # Act
        merge_all(df, merge_path, simple=True)
        
        # Assert
        assert os.path.exists(merge_path)
        merged_df = pd.read_csv(merge_path)
        assert len(merged_df) == 4
        assert "isMissing" not in merged_df.columns # Because simple mode drops it

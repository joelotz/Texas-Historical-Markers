import pytest
import pandas as pd
import json

@pytest.fixture
def sample_atlas_df():
    """Provides a sample DataFrame representing atlas_db.csv for testing."""
    data = {
        "ref:US-TX:thc": pd.Series([1001, 1002, 1003], dtype="Int32"),
        "ref:hmdb": pd.Series([5001, 5002, pd.NA], dtype="Int32"),
        "name": ["Marker A", "Marker B", "Marker C"],
        "hmdb:Latitude": [30.1, 30.2, 30.3],
        "hmdb:Longitude": [-97.1, -97.2, -97.3],
        "start_date": pd.Series([1950, 1960, 1970], dtype="Int32"),
        "website": ["http://thc.texas.gov/1", "http://thc.texas.gov/2", ""],
        "isOSM": pd.Series([True, False, False], dtype="boolean"),
        "isMissing": pd.Series([False, False, True], dtype="boolean"),
        "isPrivate": pd.Series([False, True, False], dtype="boolean"),
        "addr:county": ["Travis", "Travis", "Williamson"],
        "addr:city": ["Austin", "Austin", "Round Rock"]
    }
    return pd.DataFrame(data)

@pytest.fixture
def dummy_hmdb_csv(tmp_path):
    """Creates a temporary CSV file mimicking HMDB bulk export format."""
    file_path = tmp_path / "hmdb_export.csv"
    content = (
        "MarkerID,Marker No.,Title,Erected By,Latitude (minus=S),Longitude (minus=W),"
        "Street Address,City or Town,County or Parish,Missing,ExtraCol\n"
        "5001,1001,Title A,State of Texas,30.1,-97.1,123 Main,Austin,Travis,False,Extra\n"
        "5002,1002,Title B,Texas Historical Commission,30.2,-97.2,456 Elm,Austin,Travis,True,\n"
    )
    file_path.write_text(content)
    return str(file_path)

@pytest.fixture
def dummy_geojson_file(tmp_path):
    """Creates a temporary GeoJSON file representing markers already in OSM."""
    file_path = tmp_path / "osm_extract.geojson"
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ref:US-TX:thc": "1001"
                }
            }
        ]
    }
    with open(file_path, "w") as f:
        json.dump(data, f)
    
    return str(file_path)

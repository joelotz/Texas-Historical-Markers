from thc_toolkit import sqlite_sync, sqlite_viewer


def test_sqlite_viewer_starts_blank(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"
    sample_atlas_df.to_csv(csv_path, index=False)
    sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    payload = sqlite_viewer.query_rows(sqlite_path)

    assert payload["rows"] == []
    assert payload["total"] == 0
    assert "name" in payload["columns"]


def test_sqlite_viewer_filters_by_county_and_city(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"
    sample_atlas_df.to_csv(csv_path, index=False)
    sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    payload = sqlite_viewer.query_rows(sqlite_path, county="Travis", city="Austin")

    assert payload["total"] == 2
    assert len(payload["rows"]) == 2
    assert all(row["addr:county"] == "Travis" for row in payload["rows"])
    assert all(row["addr:city"] == "Austin" for row in payload["rows"])


def test_sqlite_viewer_supports_multiple_selected_counties(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"
    sample_atlas_df.to_csv(csv_path, index=False)
    sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    payload = sqlite_viewer.query_rows(sqlite_path, county=["Travis", "Williamson"])

    assert payload["total"] == 3
    assert {row["addr:county"] for row in payload["rows"]} == {"Travis", "Williamson"}


def test_sqlite_viewer_distinct_options_return_sorted_values(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"
    sample_atlas_df.to_csv(csv_path, index=False)
    sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    counties = sqlite_viewer._distinct_values(sqlite_path, "addr:county")
    cities = sqlite_viewer._distinct_values(sqlite_path, "addr:city")

    assert counties == ["Travis", "Williamson"]
    assert cities == ["Austin", "Round Rock"]


def test_sqlite_viewer_page_includes_column_filters_and_sorting():
    page = sqlite_viewer._page_html("atlas_db.sqlite", "atlas")

    assert 'id="filterRow"' in page
    assert "th.className = 'sortable'" in page
    assert "Filter " in page
    assert "Blank only" in page
    assert 'value="2000"' in page


def test_sqlite_viewer_resolves_default_repo_root_path(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "atlas_db.sqlite"
    sqlite_path.write_bytes(b"")
    monkeypatch.chdir(tmp_path)

    resolved = sqlite_viewer.resolve_default_sqlite_path()

    assert resolved == str(sqlite_path.resolve())

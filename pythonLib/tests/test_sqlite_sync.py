import sqlite3

import pandas as pd
import pytest

from thc_toolkit import sqlite_sync


def test_sqlite_sync_round_trip(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"
    exported_csv = tmp_path / "atlas_roundtrip.csv"

    sample_atlas_df.to_csv(csv_path, index=False)

    build_report = sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)
    assert build_report["rows"] == len(sample_atlas_df)
    assert sqlite_path.exists()

    export_df = sqlite_sync.export_csv_from_sqlite(sqlite_path, exported_csv)
    assert len(export_df) == len(sample_atlas_df)

    verify_report = sqlite_sync.verify_sqlite_sync(csv_path, sqlite_path)
    assert verify_report["match"] is True

    source = pd.read_csv(csv_path)
    exported = pd.read_csv(exported_csv)
    assert list(source.columns) == list(exported.columns)

    for column in sqlite_sync.DEFAULT_KEY_COLUMNS:
        assert (
            source[column].astype("string").tolist()
            == exported[column].astype("string").tolist()
        )


def test_sqlite_sync_build_allows_duplicate_key_values(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "dupe.csv"
    sqlite_path = tmp_path / "dupe.sqlite"

    dupe = sample_atlas_df.copy()
    dupe.loc[1, "ref:hmdb"] = dupe.loc[0, "ref:hmdb"]
    dupe.to_csv(csv_path, index=False)

    report = sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    assert report["rows"] == len(dupe)
    assert sqlite_path.exists()


def test_sqlite_sync_build_strict_ids_rejects_duplicates(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "dupe.csv"
    sqlite_path = tmp_path / "dupe.sqlite"

    dupe = sample_atlas_df.copy()
    dupe.loc[1, "ref:hmdb"] = dupe.loc[0, "ref:hmdb"]
    dupe.to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="duplicate values in ref:hmdb"):
        sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path, strict_ids=True)


def test_sqlite_sync_verify_detects_key_mismatch(sample_atlas_df, tmp_path):
    csv_path = tmp_path / "atlas.csv"
    sqlite_path = tmp_path / "atlas.sqlite"

    sample_atlas_df.to_csv(csv_path, index=False)
    sqlite_sync.build_sqlite_from_csv(csv_path, sqlite_path)

    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            'UPDATE "atlas" SET "ref:hmdb" = ? WHERE rowid = ?',
            (9999, 1),
        )
        conn.commit()

    with pytest.raises(ValueError, match="row mismatch detected"):
        sqlite_sync.verify_sqlite_sync(csv_path, sqlite_path)

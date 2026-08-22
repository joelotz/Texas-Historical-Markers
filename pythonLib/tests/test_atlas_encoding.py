"""Encoding and column-width validation for atlas_db.csv."""
import pytest

# --- column width checks (added 2026-08-22) -----------------------------------
# A spreadsheet save-back once appended ten empty columns to every row of
# atlas_db.csv. Encoding and line endings were pristine, so validate passed
# while two marker inscriptions sat outside Marker Text.

def _run_validate(path):
    import argparse
    from thc_toolkit import atlas_cli
    return atlas_cli.run_validate(argparse.Namespace(path=str(path)))


def test_validate_rejects_trailing_phantom_columns(tmp_path):
    p = tmp_path / "atlas_db.csv"
    p.write_text("a,b,c,,,\n1,2,3,,,\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _run_validate(p)
    assert e.value.code == 1


def test_validate_rejects_ragged_row(tmp_path):
    p = tmp_path / "atlas_db.csv"
    p.write_text("a,b,c\n1,2,3\n4,5,6,7\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _run_validate(p)
    assert e.value.code == 1


def test_validate_counts_quoted_commas_and_newlines_as_one_field(tmp_path):
    # Marker Text routinely contains both; a naive comma split would flag these.
    p = tmp_path / "atlas_db.csv"
    p.write_text('a,b,c\n1,"has, comma",3\n4,"has\nnewline",6\n', encoding="utf-8")
    _run_validate(p)          # must not raise


def test_validate_accepts_a_clean_file(tmp_path):
    p = tmp_path / "atlas_db.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    _run_validate(p)

import csv

import pytest

from thc_toolkit import hmdb_sync


ATLAS_HEADER = (
    "ref:US-TX:thc,ref:hmdb,name,OsmNodeID,website,memorial:website,start_date,"
    "isActive,isHMDB,isMissing,isPending,isOSM,isPrivate,addr:full,addr:city,"
    "addr:county,UTM Zone,UTM Easting,UTM Northing,estimated:Latitude,estimated:Longitude,"
    "verified:Latitude,verified:Longitude,Recorded Texas Historic Landmark,"
    "thc:designation,Marker Notes,wikimedia_commons,subject:wikimedia_commons,"
    "subject:wikipedia,subject:wikidata,Marker Text,inscription_size,DATA_NOTE"
)


def _atlas(tmp_path, rows):
    path = tmp_path / "atlas_db.csv"
    width = len(ATLAS_HEADER.split(","))
    lines = [ATLAS_HEADER]
    for thc, ref_hmdb, name in rows:
        cells = [""] * width
        cells[0], cells[1], cells[2] = thc, ref_hmdb, name
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _hmdb(tmp_path, rows):
    path = tmp_path / "hmdb.csv"
    lines = [
        "MarkerID,Marker No.,Title,Erected By,Latitude (minus=S),"
        "Longitude (minus=W),Street Address,City or Town,County or Parish,"
        "Missing,Link"
    ]
    for marker_id, marker_no, title in rows:
        lines.append(
            f"{marker_id},{marker_no},{title},Texas Historical Commission,"
            f"30.0,-97.0,1 Main St,Austin,Travis County,,"
            f"https://www.hmdb.org/m.asp?m={marker_id}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _ignore(tmp_path, marker_ids, name=hmdb_sync.IGNORE_FILE_NAME):
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["hmdb_MarkerID", "duplicates_thc", "note"],
            lineterminator="\n")
        w.writeheader()
        for marker_id in marker_ids:
            w.writerow({"hmdb_MarkerID": marker_id, "duplicates_thc": "1001",
                        "note": "duplicate page"})
    return path


def test_load_ignored_marker_ids_reads_the_id_column(tmp_path):
    path = _ignore(tmp_path, ["5002", "5003"])
    assert hmdb_sync.load_ignored_marker_ids(path) == {"5002", "5003"}


def test_load_ignored_marker_ids_tolerates_a_missing_file(tmp_path):
    assert hmdb_sync.load_ignored_marker_ids(tmp_path / "nope.csv") == set()
    assert hmdb_sync.load_ignored_marker_ids(None) == set()


def test_reconcile_skips_ignored_marker_ids(tmp_path):
    """A listed MarkerID must not surface as a conflict or a candidate."""
    atlas = _atlas(tmp_path, [("1001", "5001", "Marker A")])
    # 5002 is a second hmdb page for the same Marker No. the atlas documents
    # via 5001 -- exactly the duplicate the ignore file exists to silence.
    hmdb = _hmdb(tmp_path, [("5001", "1001", "Marker A"),
                            ("5002", "1001", "Marker A")])
    out = tmp_path / "out"
    out.mkdir()

    before = hmdb_sync.reconcile(hmdb, atlas, out, make_backup=False)
    assert before["ignored"] == 0
    assert before["conflicts"] == 1

    _ignore(tmp_path, ["5002"])
    after = hmdb_sync.reconcile(hmdb, atlas, out, make_backup=False)
    assert after["ignored"] == 1
    assert after["conflicts"] == 0
    assert after["already_documented"] == 1


def test_reconcile_finds_the_ignore_file_next_to_the_atlas(tmp_path):
    atlas = _atlas(tmp_path, [("1001", "5001", "Marker A")])
    hmdb = _hmdb(tmp_path, [("5002", "1001", "Marker A")])
    out = tmp_path / "out"
    out.mkdir()

    _ignore(tmp_path, ["5002"])          # default location: atlas's directory
    stats = hmdb_sync.reconcile(hmdb, atlas, out, make_backup=False)
    assert stats["ignored"] == 1


def test_ignore_is_keyed_on_marker_id_not_marker_no(tmp_path):
    """hmdb typos Marker No., so the skip must not key on it.

    5002 is filed under Marker No. 1002 but really duplicates thc#1001. It is
    still skipped, and the unrelated entry under 1002 is left alone.
    """
    atlas = _atlas(tmp_path, [("1001", "5001", "Marker A"),
                              ("1002", "", "Marker B")])
    hmdb = _hmdb(tmp_path, [("5002", "1002", "Marker A"),
                            ("5009", "1002", "Marker B")])
    out = tmp_path / "out"
    out.mkdir()

    _ignore(tmp_path, ["5002"])
    stats = hmdb_sync.reconcile(hmdb, atlas, out, make_backup=False)
    assert stats["ignored"] == 1
    # 5009 still reaches classification and links to the free row.
    assert stats["ignored"] + stats["thc_in_atlas"] == 2


def test_real_ignore_file_is_well_formed():
    """The tracked hmdb_ignore.csv must parse and hold unique MarkerIDs."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / hmdb_sync.IGNORE_FILE_NAME
    if not path.exists():
        pytest.skip("hmdb_ignore.csv not present")

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "ignore file is empty"

    ids = [r["hmdb_MarkerID"].strip() for r in rows]
    assert all(ids), "every row needs an hmdb_MarkerID"
    assert len(ids) == len(set(ids)), "duplicate MarkerIDs in the ignore file"
    assert all(r["duplicates_thc"].strip().isdigit() for r in rows), \
        "duplicates_thc must name the THC number the entry duplicates"

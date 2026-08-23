"""Reconcile classification for hmdb -> atlas sync."""
from thc_toolkit import hmdb_sync

# --- MarkerID held by a sibling row (added 2026-08-22) ------------------------
# Two physical markers can share one THC Marker No. -- a second casting, or one
# plaque hmdb files twice. The second lives on its own atlas row, often with a
# blank ref:US-TX:thc, which the by-THC index drops. Before this, its hmdb page
# was reported as a conflict on every run and could never be cleared, because
# ignore-listing an id a row actually carries is forbidden.

def _write(tmp_path, atlas_rows, hmdb_rows):
    import csv as _csv
    atlas = tmp_path / "atlas_db.csv"
    acols = ["ref:US-TX:thc", "ref:hmdb", "name", "memorial:website", "isHMDB", "isMissing",
             "isPending", "addr:full", "addr:city", "verified:Latitude", "verified:Longitude",
             "Marker Notes"]
    with atlas.open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=acols, lineterminator="\n")
        w.writeheader()
        for r in atlas_rows:
            w.writerow({c: r.get(c, "") for c in acols})
    hmdb = tmp_path / "hmdb.csv"
    hcols = ["MarkerID", "Marker No.", "Title", "Erected By", "Latitude (minus=S)",
             "Longitude (minus=W)", "Street Address", "City or Town", "County or Parish",
             "Missing", "Link"]
    with hmdb.open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=hcols, lineterminator="\n")
        w.writeheader()
        for r in hmdb_rows:
            w.writerow({c: r.get(c, "") for c in hcols})
    return atlas, hmdb


def test_markerid_on_a_sibling_row_is_documented_not_a_conflict(tmp_path):
    atlas, hmdb = _write(
        tmp_path,
        [{"ref:US-TX:thc": "493", "ref:hmdb": "308403", "name": "Brazos Indian Reservation School"},
         {"ref:US-TX:thc": "",    "ref:hmdb": "307871", "name": "Brazos Indian Reservation School"}],
        [{"MarkerID": "307871", "Marker No.": "493", "Title": "Brazos Indian Reservation School",
          "Erected By": "Texas Historical Commission"}],
    )
    stats = hmdb_sync.reconcile(hmdb, atlas, tmp_path / "out", make_backup=False,
                                ignore_path=tmp_path / "none.csv")
    assert stats["conflicts"] == 0
    assert stats["already_documented"] == 1


def test_genuinely_unknown_markerid_is_still_a_conflict(tmp_path):
    atlas, hmdb = _write(
        tmp_path,
        [{"ref:US-TX:thc": "493", "ref:hmdb": "308403", "name": "Brazos Indian Reservation School"}],
        [{"MarkerID": "999999", "Marker No.": "493", "Title": "Something Else Entirely",
          "Erected By": "Texas Historical Commission"}],
    )
    stats = hmdb_sync.reconcile(hmdb, atlas, tmp_path / "out", make_backup=False,
                                ignore_path=tmp_path / "none.csv")
    assert stats["conflicts"] == 1

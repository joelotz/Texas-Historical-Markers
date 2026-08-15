"""Invariants that have each been violated in production without anything noticing.

Every case here is drawn from a real 2026-08-15 failure, not invented:

* hmdb merged duplicate pages into canonical ones, leaving 13 ignore entries
  naming ids the atlas actively used.
* 29 of 41 ignore entries pointed at re-catalogued MarkerIDs, so reconcile had
  silently stopped skipping them.
* Seven OSM nodes carried ref:hmdb="202023.0" from a pandas float.
"""
import csv

import pandas as pd
import pytest

from thc_toolkit import atlas_check
from thc_toolkit.hmdb_sync import IGNORE_FILE_NAME

COLS = ["ref:US-TX:thc", "ref:hmdb", "name", "OsmNodeID", "memorial:website"]


def _atlas_df(rows):
    return pd.DataFrame([dict(zip(COLS, r)) for r in rows], columns=COLS).fillna("")


def _write_atlas(tmp_path, rows):
    p = tmp_path / "atlas_db.csv"
    _atlas_df(rows).to_csv(p, index=False, lineterminator="\n")
    return p


def _write_ignore(tmp_path, marker_ids):
    p = tmp_path / IGNORE_FILE_NAME
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["hmdb_MarkerID", "duplicates_thc", "note"],
                           lineterminator="\n")
        w.writeheader()
        for mid in marker_ids:
            w.writerow({"hmdb_MarkerID": mid, "duplicates_thc": "1", "note": "dup"})
    return p


def _site(ref):
    return atlas_check.WEBSITE_TEMPLATE.format(ref)


# --- ignore list must not name a MarkerID the atlas uses --------------------

def test_ignore_entry_naming_a_live_atlas_ref_is_an_error():
    atlas = _atlas_df([("4069", "307892", "Poolville", "", _site("307892"))])
    problems = atlas_check.check_ignore_not_claimed_by_atlas(atlas, {"307892"})
    assert len(problems) == 1
    assert "307892" in problems[0] and "thc#4069" in problems[0]


def test_ignore_entry_for_an_unused_marker_id_is_fine():
    atlas = _atlas_df([("4069", "307892", "Poolville", "", _site("307892"))])
    assert atlas_check.check_ignore_not_claimed_by_atlas(atlas, {"270620"}) == []


def test_blank_atlas_refs_are_not_treated_as_a_clash():
    atlas = _atlas_df([("4069", "", "Poolville", "", "")])
    assert atlas_check.check_ignore_not_claimed_by_atlas(atlas, {""}) == []


# --- memorial:website must agree with ref:hmdb ------------------------------

def test_website_pointing_at_a_different_marker_is_an_error():
    atlas = _atlas_df([("1", "307880", "Post Hospital", "", _site("307879"))])
    problems = atlas_check.check_memorial_website_matches_ref(atlas)
    assert len(problems) == 1 and "307879" in problems[0]


def test_float_formatted_ref_is_caught_by_the_website_check():
    atlas = _atlas_df([("1", "202023.0", "Presbyterian Church", "", _site("202023"))])
    assert atlas_check.check_memorial_website_matches_ref(atlas)


def test_matching_website_passes_and_blank_website_is_skipped():
    atlas = _atlas_df([
        ("1", "307880", "A", "", _site("307880")),
        ("2", "307881", "B", "", ""),
    ])
    assert atlas_check.check_memorial_website_matches_ref(atlas) == []


# --- duplicate THC groups ---------------------------------------------------

def test_duplicate_thc_group_with_a_blank_ref_is_an_error():
    atlas = _atlas_df([
        ("493", "307872", "Brazos", "", _site("307872")),
        ("493", "", "Brazos", "", ""),
    ])
    problems = atlas_check.check_duplicate_thc_groups(atlas)
    assert len(problems) == 1 and "blank ref:hmdb" in problems[0]


def test_duplicate_thc_group_repeating_a_ref_is_an_error():
    atlas = _atlas_df([
        ("493", "307872", "Brazos", "", _site("307872")),
        ("493", "307872", "Brazos", "", _site("307872")),
    ])
    problems = atlas_check.check_duplicate_thc_groups(atlas)
    assert len(problems) == 1 and "repeat" in problems[0]


def test_duplicate_thc_group_with_distinct_refs_is_legitimate():
    """thc#10596 Annunciation Church really is two markers, one entry each."""
    atlas = _atlas_df([
        ("10596", "307875", "Annunciation Church", "1", _site("307875")),
        ("10596", "307874", "Annunciation Church", "2", _site("307874")),
    ])
    assert atlas_check.check_duplicate_thc_groups(atlas) == []


def test_two_thc_numbers_sharing_one_ref_is_not_a_duplicate_group():
    """thc#6815 and thc#13464 are separate markers sharing one hmdb entry."""
    atlas = _atlas_df([
        ("6815", "307920", "Perry Cemetery", "1", _site("307920")),
        ("13464", "307920", "Perry Cemetery", "2", _site("307920")),
    ])
    assert atlas_check.check_duplicate_thc_groups(atlas) == []


# --- liveness against an hmdb snapshot --------------------------------------

def _write_snapshot(tmp_path, marker_ids):
    p = tmp_path / "hmdb.csv"
    p.write_text("MarkerID,Marker No.,Title\n"
                 + "".join(f"{m},1,T\n" for m in marker_ids), encoding="utf-8")
    return p


def test_dead_atlas_ref_and_dead_ignore_entry_are_both_reported(tmp_path):
    atlas = _atlas_df([("1", "218654", "gone", "", _site("218654"))])
    snap = _write_snapshot(tmp_path, ["307872"])
    problems = atlas_check.check_refs_live(atlas, {"200387"}, snap)
    assert len(problems) == 2
    assert any("atlas ref:hmdb" in p and "218654" in p for p in problems)
    assert any(IGNORE_FILE_NAME in p and "200387" in p for p in problems)


def test_live_references_pass(tmp_path):
    atlas = _atlas_df([("1", "307872", "here", "", _site("307872"))])
    snap = _write_snapshot(tmp_path, ["307872", "200387"])
    assert atlas_check.check_refs_live(atlas, {"200387"}, snap) == []


# --- the float-formatted tag guard ------------------------------------------

@pytest.mark.parametrize("tags", [
    {"ref:hmdb": "202023.0"},
    {"memorial:website": "https://www.hmdb.org/m.asp?m=202023.0"},
    {"ref:hmdb": "202023", "memorial:website": "https://www.hmdb.org/m.asp?m=96134.0"},
])
def test_float_formatted_tags_are_rejected(tags):
    with pytest.raises(ValueError, match="float-formatted"):
        atlas_check.assert_no_float_formatted_tags(tags)


@pytest.mark.parametrize("tags", [
    {"ref:hmdb": "202023", "memorial:website": "https://www.hmdb.org/m.asp?m=202023"},
    {"addr:full": "1.0 mile north of town"},          # prose, not an id
    {"name": "Version 2.0 Marker"},
    {},
])
def test_legitimate_tags_pass_the_float_guard(tags):
    atlas_check.assert_no_float_formatted_tags(tags)


def test_build_osmchange_refuses_float_formatted_tags():
    from thc_toolkit.osm_refix_direct import build_osmchange
    update = {"node_id": 1, "version": 1, "lat": "30.0", "lon": "-97.0",
              "tags": {"ref:hmdb": "202023.0"}}
    with pytest.raises(ValueError, match="float-formatted"):
        build_osmchange([update], 999)


def test_build_osmchange_still_works_for_clean_tags():
    from thc_toolkit.osm_refix_direct import build_osmchange
    update = {"node_id": 1, "version": 1, "lat": "30.0", "lon": "-97.0",
              "tags": {"ref:hmdb": "202023"}}
    assert b'v="202023"' in build_osmchange([update], 999)


# --- end to end -------------------------------------------------------------

def test_run_check_exits_nonzero_when_an_invariant_is_broken(tmp_path, capsys):
    path = _write_atlas(tmp_path, [("4069", "307892", "Poolville", "", _site("307892"))])
    _write_ignore(tmp_path, ["307892"])

    class A:
        pass
    a = A()
    a.path, a.ignore, a.hmdb = str(path), None, None
    with pytest.raises(SystemExit) as e:
        atlas_check.run_check(a)
    assert e.value.code == 1
    assert "FAIL" in capsys.readouterr().out


def test_run_check_passes_on_a_healthy_atlas(tmp_path, capsys):
    path = _write_atlas(tmp_path, [("4069", "307892", "Poolville", "", _site("307892"))])
    _write_ignore(tmp_path, ["270620"])

    class A:
        pass
    a = A()
    a.path, a.ignore, a.hmdb = str(path), None, None
    atlas_check.run_check(a)
    out = capsys.readouterr().out
    assert "FAIL" not in out

"""The post-state check for OSM ref rewrites.

Added 2026-08-22 after a plan to retag 11 nodes passed two agreeing checks and
would still have created 11 duplicate refs: both checks confirmed the node's
identity, neither asked whether that identity was already mapped elsewhere.
"""
import pytest

from thc_toolkit.osm_refix_direct import RefPlanError, validate_ref_plan


def test_rejects_a_retag_onto_an_already_held_ref():
    world = {111: {"ref:US-TX:thc": "9837"}, 222: {"ref:US-TX:thc": "7814"}}
    updates = [{"node_id": 111, "tags": {"ref:US-TX:thc": "7814"}}]   # 222 already has it
    with pytest.raises(RefPlanError) as e:
        validate_ref_plan(updates, world)
    assert "7814" in str(e.value) and "111" in str(e.value) and "222" in str(e.value)


def test_allows_a_retag_onto_a_free_ref():
    world = {111: {"ref:US-TX:thc": "9837"}, 222: {"ref:US-TX:thc": "7814"}}
    updates = [{"node_id": 111, "tags": {"ref:US-TX:thc": "4803"}}]
    assert validate_ref_plan(updates, world)["nodes_written"] == 1


def test_allows_a_swap_between_two_nodes():
    """Both move at once, so neither ref is ever doubly held afterwards."""
    world = {111: {"ref:US-TX:thc": "A"}, 222: {"ref:US-TX:thc": "B"}}
    updates = [{"node_id": 111, "tags": {"ref:US-TX:thc": "B"}},
               {"node_id": 222, "tags": {"ref:US-TX:thc": "A"}}]
    assert validate_ref_plan(updates, world)["nodes_written"] == 2


def test_position_only_edit_keeping_its_own_ref_is_fine():
    world = {111: {"ref:US-TX:thc": "239"}}
    updates = [{"node_id": 111, "tags": {"ref:US-TX:thc": "239"}}]
    assert validate_ref_plan(updates, world)["nodes_written"] == 1


def test_dropping_a_ref_frees_it():
    world = {111: {"ref:US-TX:thc": "500"}, 222: {"ref:US-TX:thc": "600"}}
    updates = [{"node_id": 111, "tags": {}},
               {"node_id": 222, "tags": {"ref:US-TX:thc": "500"}}]
    assert validate_ref_plan(updates, world)["refs_after"] == 1


def test_the_real_2026_08_22_plan_would_have_been_rejected():
    world = {12438024539: {"ref:US-TX:thc": "9837"}, 13988599835: {"ref:US-TX:thc": "7814"},
             12452329769: {"ref:US-TX:thc": "3819"}, 13988618805: {"ref:US-TX:thc": "1828"}}
    updates = [{"node_id": 12438024539, "tags": {"ref:US-TX:thc": "7814"}},
               {"node_id": 12452329769, "tags": {"ref:US-TX:thc": "1828"}}]
    with pytest.raises(RefPlanError) as e:
        validate_ref_plan(updates, world)
    assert "2 ref(s)" in str(e.value)

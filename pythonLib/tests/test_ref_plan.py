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


def test_shared_ref_must_be_declared_not_assumed():
    """thc#5448 really is on two nodes -- but the caller has to say so."""
    world = {111: {"ref:US-TX:thc": "5448"}, 222: {"ref:US-TX:thc": "13294"}}
    updates = [{"node_id": 222, "tags": {"ref:US-TX:thc": "5448"}}]
    with pytest.raises(RefPlanError):
        validate_ref_plan(updates, world)
    ok = validate_ref_plan(updates, world, allow_shared={"5448"})
    assert ok["shared_allowed"] == ["5448"]


def test_allow_shared_does_not_excuse_other_collisions():
    world = {111: {"ref:US-TX:thc": "5448"}, 222: {"ref:US-TX:thc": "999"},
             333: {"ref:US-TX:thc": "111"}}
    updates = [{"node_id": 222, "tags": {"ref:US-TX:thc": "5448"}},
               {"node_id": 333, "tags": {"ref:US-TX:thc": "999"}}]
    world[444] = {"ref:US-TX:thc": "999"}
    with pytest.raises(RefPlanError) as e:
        validate_ref_plan(updates, world, allow_shared={"5448"})
    assert "999" in str(e.value) and "5448" not in str(e.value)


def test_preexisting_collisions_are_reported_not_raised():
    """A plan is judged by what it causes, not by mess it never touched."""
    world = {1: {"ref:US-TX:thc": "A"}, 2: {"ref:US-TX:thc": "A"},   # already shared
             3: {"ref:US-TX:thc": "B"}}
    updates = [{"node_id": 3, "tags": {"ref:US-TX:thc": "C"}}]
    res = validate_ref_plan(updates, world)
    assert res["preexisting_shared"] == {"A": [1, 2]}


def test_adding_a_third_node_to_an_existing_collision_still_raises():
    world = {1: {"ref:US-TX:thc": "A"}, 2: {"ref:US-TX:thc": "A"}, 3: {"ref:US-TX:thc": "B"}}
    updates = [{"node_id": 3, "tags": {"ref:US-TX:thc": "A"}}]
    with pytest.raises(RefPlanError):
        validate_ref_plan(updates, world)

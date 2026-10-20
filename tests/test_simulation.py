"""Determinism, branch isolation, invariants and action preconditions."""

import dataclasses

import pytest
from timeshift.sim.actions import Action, apply_action, validate_action
from timeshift.sim.fork import fork_reality
from timeshift.sim.model import ModuleStatus
from timeshift.sim.physics import simulate, step
from timeshift.sim.scenarios import SCENARIOS, load_scenario

SOLAR_CANDIDATES = [Action("activate_backup_power"),
                    Action("repair_solar_array", {"crew_id": "C3"}),
                    Action("isolate_module", {"module_id": "HAB"})]


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_same_seed_same_trajectory(sid):
    a = simulate(load_scenario(sid).state, 40)
    b = simulate(load_scenario(sid).state, 40)
    assert [s.state_hash() for s in a] == [s.state_hash() for s in b]


def test_different_seed_changes_leak_trajectory():
    a = simulate(load_scenario("oxygen_leak", seed=1).state, 20)[-1]
    b = simulate(load_scenario("oxygen_leak", seed=2).state, 20)[-1]
    assert a.oxygen_reserve_kg != b.oxygen_reserve_kg


def test_fork_does_not_mutate_canonical_state():
    s = load_scenario("solar_cascade").state
    before = s.state_hash()
    fork_reality(s, SOLAR_CANDIDATES, horizon=20)
    assert s.state_hash() == before
    assert s.tick == 0 and s.revision == 0


def test_branches_are_independent_and_replayable():
    s = load_scenario("solar_cascade").state
    r1 = fork_reality(s, SOLAR_CANDIDATES, horizon=20)
    # Same candidate alone gives the identical branch -> branches do not leak into each other.
    solo = fork_reality(s, [SOLAR_CANDIDATES[2]], horizon=20)
    assert r1.branches[3].trajectory[-1].state_hash() == solo.branches[1].trajectory[-1].state_hash()
    r2 = fork_reality(s, SOLAR_CANDIDATES, horizon=20)
    assert [b.outcome for b in r1.branches] == [b.outcome for b in r2.branches]


def test_all_branches_share_horizon_and_origin():
    s = load_scenario("solar_cascade").state
    r = fork_reality(s, SOLAR_CANDIDATES, horizon=15)
    assert all(len(b.trajectory) == 15 for b in r.branches if b.legal)
    assert all(b.trajectory[-1].tick == 15 for b in r.branches if b.legal)
    assert r.origin_hash == s.state_hash() and r.seed == s.seed


def test_state_is_frozen():
    s = load_scenario("solar_cascade").state
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.tick = 5  # type: ignore[misc]


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_numeric_invariants_hold(sid):
    s = load_scenario(sid).state
    for st in simulate(s, 120):
        assert 0 <= st.oxygen_reserve_kg <= st.oxygen_capacity_kg
        assert 0 <= st.power_reserve_kwh <= st.power_capacity_kwh
        assert st.backup_charge_kwh >= 0
        assert all(0 <= c.health_pct <= 100 for c in st.crew)
        assert all(0 <= m.integrity_pct <= 100 for m in st.modules)


def test_max_three_candidates():
    s = load_scenario("solar_cascade").state
    with pytest.raises(ValueError):
        fork_reality(s, SOLAR_CANDIDATES + [Action("vent_reactor")])


@pytest.mark.parametrize("action,fragment", [
    (Action("isolate_module", {"module_id": "AIRLOCK_B"}), "does not exist"),
    (Action("isolate_module", {"module_id": "LIFE_SUPPORT"}), "life-critical"),
    (Action("isolate_module", {}), "missing argument"),
    (Action("launch_rocket", {}), "unknown tool"),
    (Action("reroute_power", {"source_module": "LIFE_SUPPORT", "target_module": "LAB"}),
     "life-critical"),
    (Action("reroute_power", {"source_module": "LAB", "target_module": "LAB"}), "must differ"),
    (Action("repair_solar_array", {"crew_id": "C9"}), "does not exist"),
    (Action("isolate_module", {"module_id": 5}), "must be str"),
])
def test_invalid_actions_rejected_with_reasons(action, fragment):
    errs = validate_action(load_scenario("solar_cascade").state, action)
    assert errs and any(fragment in e for e in errs), errs


def test_vent_blocked_while_crew_in_reactor():
    s = load_scenario("reactor_overheat").state
    assert any("crew are inside REACTOR" in e for e in validate_action(s, Action("vent_reactor")))


def test_isolation_stops_leak_and_relocates_crew():
    s = load_scenario("oxygen_leak").state
    s2 = apply_action(s, Action("isolate_module", {"module_id": "GREENHOUSE"}))
    assert s2.module("GREENHOUSE").status == ModuleStatus.ISOLATED
    assert s2.crew_member("C4").location != "GREENHOUSE"
    assert step(s2).oxygen_reserve_kg > step(s).oxygen_reserve_kg


def test_signature_scenario_unsupported_branch_ranks_first():
    """The ungrounded HAB isolation *looks* best to the simulator -- that is the point of
    the signature demo: numbers alone do not reveal an unsupported premise."""
    r = fork_reality(load_scenario("solar_cascade").state, SOLAR_CANDIDATES, horizon=20)
    ranked = r.ranked()
    assert ranked[0].action == Action("isolate_module", {"module_id": "HAB"})
    assert all(b.outcome.score > r.baseline().outcome.score for b in ranked)


def test_reactor_reroute_avoids_scram_noop_does_not():
    r = fork_reality(load_scenario("reactor_overheat").state,
                     [Action("reroute_power", {"source_module": "LAB", "target_module": "REACTOR"})])
    assert r.baseline().outcome.reactor_online is False
    assert r.branches[1].outcome.reactor_online is True

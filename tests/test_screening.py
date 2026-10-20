"""Every forked branch is gated before selection; cached decisions are revision-bound.

Uses the labelled TEST DOUBLE from test_mission (no model)."""

from types import SimpleNamespace

from counterfactual_decision_gate import Verdict
from counterfactual_decision_gate.strands_handler import CounterfactualGateHandler
from strands.interventions import Guide, Proceed
from test_mission import mission, prop

from timeshift.explain import ConsequenceExplanation, RejectedBranch, consistency_issues

HAB_LOW = lambda s: 0.2 if "PROPOSED ACTION: isolate_module" in s else 0.9  # noqa: E731


def _forked():
    m, client = mission(grounded=HAB_LOW)
    props = [prop(m, "activate_backup_power"), prop(m, "repair_solar_array", {"crew_id": "C3"}),
             prop(m, "isolate_module", {"module_id": "HAB"}, refs=("R-HAB-01",))]
    fork_id, _ = m.fork(props)
    return m, client, props, fork_id


def test_screen_gates_every_branch_once():
    m, client, props, fork_id = _forked()
    out = m.screen(fork_id)
    assert len(client.states) == 3
    assert out["isolate_module(module_id=HAB)"].verdict == Verdict.DENY
    assert out["activate_backup_power()"].verdict == Verdict.PROCEED
    assert m.events[-1].type == "fork.screened"


def test_cached_decision_is_invalidated_by_a_commit():
    m, _, props, fork_id = _forked()
    m.screen(fork_id)
    assert m.cached_decision(fork_id, props[1]) is not None
    m.commit(props[0], m.cached_decision(fork_id, props[0]))
    assert m.cached_decision(fork_id, props[1]) is None     # revision moved on


def _event(args):
    return SimpleNamespace(tool_use={"name": "commit", "input": args, "toolUseId": "t1"})


def test_handler_reuses_cached_decision_without_new_inference():
    m, client, props, fork_id = _forked()
    screened = m.screen(fork_id)
    n = len(client.states)
    h = CounterfactualGateHandler(
        m.gate, build_request=lambda *a: m.gate_request(props[2], fork_id),
        gated_tools={"commit"}, cached_decision=lambda *a: screened["isolate_module(module_id=HAB)"])
    assert isinstance(h.before_tool_call(_event({})), Guide)
    assert len(client.states) == n                           # no second Decider call


def test_handler_ignores_cache_when_policy_now_fails():
    m, client, props, fork_id = _forked()
    screened = m.screen(fork_id)
    h = CounterfactualGateHandler(
        m.gate, build_request=lambda *a: m.gate_request(props[0], fork_id),
        gated_tools={"commit"}, policy_check=lambda *a: ["STALE: revision moved"],
        cached_decision=lambda *a: screened["activate_backup_power()"])
    action = h.before_tool_call(_event({}))
    assert not isinstance(action, Proceed)
    assert h.decisions[-1].hard_violations == ["STALE: revision moved"]


def test_explanation_branch_claims_must_match_record():
    packet = {"committed_branch_id": "B1", "branches": [{"branch_id": b} for b in
                                                         ("B0", "B1", "B2", "B3")]}
    ok = ConsequenceExplanation(headline="h", selected_branch="B1", why_selected="w",
                                rejected=[RejectedBranch(branch_id="B3", reason="r")],
                                limitations="l")
    assert consistency_issues(ok, packet) == []
    wrong = ok.model_copy(update={"selected_branch": "B3",
                                  "rejected": [RejectedBranch(branch_id="B1", reason="r"),
                                               RejectedBranch(branch_id="B9", reason="r")]})
    issues = consistency_issues(wrong, packet)
    assert len(issues) == 3

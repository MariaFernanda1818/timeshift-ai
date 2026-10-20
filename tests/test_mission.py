"""Orchestrator tests: temporal consistency, idempotency, fail-closed commits.

`FixedGroundingClient` is an explicitly labelled TEST DOUBLE that returns a fixed grounding
score, so deterministic orchestration can be tested without a model. Real Decider runs live
in scripts/run_signature_demo.py and the benchmark."""

import pytest
from counterfactual_decision_gate import (
    CounterfactualDecisionGate,
    DeciderClient,
    DeciderUnavailable,
    Verdict,
)
from timeshift.mission import Mission, Proposal


class FixedGroundingClient(DeciderClient):
    """TEST DOUBLE."""

    def __init__(self, grounded=0.95, fail=False):
        super().__init__(url="http://test.invalid")
        self.grounded, self.fail, self.states = grounded, fail, []

    def health(self, refresh=False):
        if self.fail:
            raise DeciderUnavailable("down")
        return {"checkpoint": "TEST-DOUBLE"}

    def ask(self, state, questions):
        self.states.append(state)
        g = self.grounded(state) if callable(self.grounded) else self.grounded
        return {"model": "TEST-DOUBLE", "latency_ms": 0.1, "usage": {"input_tokens": 1},
                "answers": {"evidence_grounded": {"noul": g},
                            "verdict": {"choice": "proceed", "confidence": 0.9,
                                        "probabilities": {"proceed": 0.9}}}}


def mission(grounded=0.95, fail=False, scenario="solar_cascade"):
    client = FixedGroundingClient(grounded, fail)
    return Mission.from_scenario(scenario, gate=CounterfactualDecisionGate(client)), client


def prop(m, tool, args=None, refs=("E000-PWR",), **kw):
    return Proposal(tool=tool, args=args or {}, rationale="test", cited_evidence=list(refs),
                    based_on_revision=kw.get("rev", m.state.revision),
                    based_on_tick=kw.get("tick", m.state.tick))


def test_commit_requires_proceed():
    m, _ = mission(grounded=0.1)
    p = prop(m, "activate_backup_power")
    d = m.evaluate(p)
    assert d.verdict == Verdict.DENY
    with pytest.raises(PermissionError):
        m.commit(p, d)
    assert m.state.revision == 0 and not m.state.backup_active


def test_commit_bumps_revision_and_mutates_only_via_orchestrator():
    m, _ = mission()
    p = prop(m, "activate_backup_power")
    m.commit(p, m.evaluate(p))
    assert m.state.revision == 1 and m.state.backup_active
    assert [e.type for e in m.events][-1] == "action.committed"


def test_stale_revision_rejected_deterministically_even_if_decider_approves():
    m, _ = mission(grounded=0.99)
    old = prop(m, "repair_solar_array", {"crew_id": "C3"})
    m.commit(prop(m, "activate_backup_power"), m.evaluate(prop(m, "activate_backup_power")))
    d = m.evaluate(old)                          # proposal still says revision 0
    assert d.verdict == Verdict.DENY
    assert any("STALE" in r for r in d.reasons)
    assert d.decider_status == "skipped"         # deterministic check, not a Decider finding


def test_stale_cited_evidence_rejected():
    m, _ = mission(grounded=0.99)
    m.advance(5)
    p = prop(m, "activate_backup_power", refs=("E000-PWR",))
    v = m.policy_violations(p)
    assert any("STALE: cited evidence E000-PWR" in x for x in v)
    fresh = prop(m, "activate_backup_power", refs=("E005-PWR",))
    assert m.policy_violations(fresh) == []


def test_nonexistent_evidence_rejected():
    m, _ = mission()
    assert any("does not exist" in x for x in
               m.policy_violations(prop(m, "activate_backup_power", refs=("E999-FAKE",))))


def test_idempotency_and_repeat_window():
    m, _ = mission()
    p = prop(m, "activate_backup_power")
    d = m.evaluate(p)
    m.commit(p, d)
    with pytest.raises(PermissionError):
        m.commit(p, d)                           # same proposal id + now stale revision


def test_decider_unavailable_fails_closed_and_abstains():
    m, _ = mission(fail=True)
    out = m.decide([prop(m, "activate_backup_power")])
    assert out["committed"] is None
    assert m.state.revision == 0
    assert m.decisions[-1]["decider_status"] == "unavailable"


def test_decide_skips_rejected_top_branch_and_commits_next():
    # Double scores low only when the HAB action is in the PROPOSED ACTION line.
    m, client = mission(grounded=lambda s: 0.2 if 'PROPOSED ACTION: isolate_module' in s else 0.9)
    props = [prop(m, "activate_backup_power"),
             prop(m, "repair_solar_array", {"crew_id": "C3"}),
             prop(m, "isolate_module", {"module_id": "HAB"}, refs=("R-HAB-01",))]
    out = m.decide(props)
    assert {"branch_id": "B3", "verdict": "DENY"} in out["tried"]
    assert len(out["tried"]) == 3
    assert out["committed"] == "B1"
    assert m.state.backup_active and m.state.module("HAB").status.value == "nominal"
    # The gate saw the simulated futures, including the alternatives.
    assert "SIMULATED FUTURES" in client.states[0] and "B0 NO-OP" in client.states[0]


def test_unknown_tool_rejected():
    m, _ = mission()
    assert m.policy_violations(prop(m, "self_destruct")) == [
        "tool 'self_destruct' is not on the allowlist"]


def test_external_recommendation_enters_fork_untrusted():
    m, _ = mission()
    ext = m.external_proposals()
    assert len(ext) == 1 and ext[0].tool == "isolate_module" and ext[0].args == {"module_id": "HAB"}
    assert ext[0].cited_evidence == ["R-HAB-01"] and "classifier" in ext[0].proposer
    assert mission(scenario="oxygen_leak")[0].external_proposals() == []

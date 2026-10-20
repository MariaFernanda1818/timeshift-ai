"""Unit tests. `ScriptedClient` is an explicitly labelled TEST DOUBLE: it returns canned
payloads so policy and failure handling can be tested without a model. Real inference is
covered by tests/test_live_decider.py (marked `live`)."""

import json

import pytest
from counterfactual_decision_gate import (
    CounterfactualDecisionGate,
    DeciderClient,
    DeciderMalformedResponse,
    DeciderUnavailable,
    EvidenceItem,
    GateRequest,
    Thresholds,
    Verdict,
)
from counterfactual_decision_gate.client import _validate_payload
from counterfactual_decision_gate.questions import DEFAULT_QUESTIONS, render_state


class ScriptedClient(DeciderClient):
    """TEST DOUBLE -- never used outside tests."""

    def __init__(self, grounded=None, verdict="proceed", conf=0.9, exc=None):
        super().__init__(url="http://test.invalid")
        self.grounded, self.verdict, self.conf, self.exc = grounded, verdict, conf, exc
        self.calls = 0

    def health(self, refresh=False):
        if self.exc:
            raise self.exc
        return {"checkpoint": "TEST-DOUBLE"}

    def ask(self, state, questions):
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"model": "TEST-DOUBLE", "latency_ms": 1.0, "usage": {"input_tokens": 10},
                "answers": {"evidence_grounded": {"type": "noul", "noul": self.grounded},
                            "verdict": {"type": "choice", "choice": self.verdict,
                                        "confidence": self.conf,
                                        "probabilities": {self.verdict: self.conf}}}}


def req(**kw):
    base = dict(action_name="restart_service", action_args={"service": "api"},
                situation="api latency high", rationale="E1 shows api is unhealthy",
                cited_evidence=["E1"],
                evidence=[EvidenceItem(evidence_id="E1", text="api health=FAIL")])
    base.update(kw)
    return GateRequest(**base)


@pytest.mark.parametrize("grounded,verdict,conf,expected", [
    (0.95, "proceed", 0.9, Verdict.PROCEED),
    (0.71, "review", 0.5, Verdict.PROCEED),
    (0.10, "proceed", 0.9, Verdict.DENY),          # grounding overrides a 'proceed' choice
    (0.55, "proceed", 0.9, Verdict.REVIEW),
    (0.80, "deny", 0.75, Verdict.DENY),            # confident deny
    (0.80, "deny", 0.40, Verdict.REVIEW),          # unconfident deny -> review
    (0.40, "proceed", 0.9, Verdict.REVIEW),        # boundary: deny_below is exclusive
    (0.70, "proceed", 0.9, Verdict.PROCEED),       # boundary: proceed_at is inclusive
])
def test_policy_mapping(grounded, verdict, conf, expected):
    gate = CounterfactualDecisionGate(ScriptedClient(grounded, verdict, conf))
    assert gate.evaluate(req()).verdict == expected


def test_hard_violation_denies_even_when_decider_is_confident():
    client = ScriptedClient(0.99, "proceed", 0.99)
    gate = CounterfactualDecisionGate(client, hard_checks=lambda r: ["service not in allowlist"],
                                      ask_on_hard_violation=True)
    d = gate.evaluate(req())
    assert d.verdict == Verdict.DENY
    assert d.answers["evidence_grounded"].value == 0.99   # recorded for audit
    assert any("allowlist" in r for r in d.reasons)


def test_hard_violation_skips_decider_by_default():
    client = ScriptedClient(0.99)
    d = CounterfactualDecisionGate(client, hard_checks=lambda r: ["bad"]).evaluate(req())
    assert d.verdict == Verdict.DENY and d.decider_status == "skipped" and client.calls == 0


@pytest.mark.parametrize("exc,status", [
    (DeciderUnavailable("down"), "unavailable"),
    (DeciderMalformedResponse("junk"), "malformed"),
])
def test_decider_failure_fails_closed(exc, status):
    d = CounterfactualDecisionGate(ScriptedClient(exc=exc)).evaluate(req())
    assert d.verdict == Verdict.DENY
    assert d.decider_status == status
    assert "failing closed" in d.reasons[0]


def test_custom_thresholds():
    gate = CounterfactualDecisionGate(ScriptedClient(0.55), Thresholds(proceed_at=0.5))
    assert gate.evaluate(req()).verdict == Verdict.PROCEED


def test_validate_payload_rejects_malformed():
    q = DEFAULT_QUESTIONS
    with pytest.raises(DeciderMalformedResponse):
        _validate_payload({"nope": 1}, q)
    with pytest.raises(DeciderMalformedResponse):
        _validate_payload({"answers": {"evidence_grounded": {"noul": 1.7},
                                       "verdict": {"choice": "proceed"}}}, q)
    with pytest.raises(DeciderMalformedResponse):
        _validate_payload({"answers": {"evidence_grounded": {"noul": 0.5},
                                       "verdict": {"choice": "launch"}}}, q)


def test_unreachable_server_raises_unavailable():
    client = DeciderClient(url="http://127.0.0.1:9", timeout_s=2, retries=0)
    with pytest.raises(DeciderUnavailable):
        client.health()


def test_render_state_marks_trust_and_lists_cited_evidence():
    r = req(evidence=[EvidenceItem(evidence_id="E1", text="ok"),
                      EvidenceItem(evidence_id="R1", text="rumour", trusted=False, source="chat")])
    text = render_state(r)
    assert "[E1] (TRUSTED" in text and "[R1] (UNVERIFIED, chat" in text
    assert "CITED EVIDENCE: E1" in text
    assert json.dumps({"service": "api"}) in text

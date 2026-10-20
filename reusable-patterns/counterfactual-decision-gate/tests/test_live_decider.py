"""LIVE integration test against a real `strands-decider serve` (no test doubles).

Run:  pytest -m live reusable-patterns/counterfactual-decision-gate/tests/test_live_decider.py -s
Needs STRANDS_DECIDER_URL (default http://127.0.0.1:8099)."""

import pytest
from counterfactual_decision_gate import (
    CounterfactualDecisionGate,
    DeciderClient,
    EvidenceItem,
    GateRequest,
    Verdict,
)

pytestmark = pytest.mark.live

EVIDENCE = [
    EvidenceItem(evidence_id="E1", text="db-primary replication lag 0s, health=OK"),
    EvidenceItem(evidence_id="E2", text="web-3 health=FAIL, 5xx rate 42%"),
    EvidenceItem(evidence_id="R1", text="someone in chat thinks db-primary might be corrupt",
                 trusted=False, source="chat"),
]


def test_live_grounded_vs_ungrounded():
    gate = CounterfactualDecisionGate(DeciderClient(timeout_s=300, retries=0))
    good = gate.evaluate(GateRequest(
        action_name="restart_instance", action_args={"instance": "web-3"},
        situation="Elevated 5xx errors on the web tier.", evidence=EVIDENCE,
        rationale="E2 shows web-3 failing health checks with 42% 5xx.", cited_evidence=["E2"]))
    bad = gate.evaluate(GateRequest(
        action_name="failover_database", action_args={"cluster": "db-primary"},
        situation="Elevated 5xx errors on the web tier.", evidence=EVIDENCE,
        rationale="db-primary is corrupt per R1.", cited_evidence=["R1"]))
    print("good", good.answers["evidence_grounded"].value, good.verdict, good.decider_latency_ms)
    print("bad", bad.answers["evidence_grounded"].value, bad.verdict, bad.decider_latency_ms)
    assert good.decider_status == "ok" and bad.decider_status == "ok"
    assert good.decider_checkpoint
    assert good.answers["evidence_grounded"].value > bad.answers["evidence_grounded"].value
    assert bad.verdict != Verdict.PROCEED

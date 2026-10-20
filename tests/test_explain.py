"""The deterministic numeric-claim check used on Bedrock explanations (no model needed)."""

from test_mission import mission, prop
from timeshift.explain import evidence_packet, unsupported_claims


def _packet():
    m, _ = mission(grounded=lambda s: 0.258 if "PROPOSED ACTION: isolate_module" in s else 0.885)
    out = m.decide([prop(m, "activate_backup_power"),
                    prop(m, "repair_solar_array", {"crew_id": "C3"}),
                    prop(m, "isolate_module", {"module_id": "HAB"}, refs=("R-HAB-01",))])
    return evidence_packet(m, out["fork_id"])


def test_packet_contains_simulated_numbers_and_verdicts():
    p = _packet()
    b3 = next(b for b in p["branches"] if b["branch_id"] == "B3")
    assert b3["gate"]["verdict"] == "DENY" and b3["gate"]["untrusted_cited"] == ["R-HAB-01"]
    assert p["ranked_by_simulated_score"][0] == "B3"


def test_grounded_text_passes():
    p = _packet()
    b1 = next(b for b in p["branches"] if b["branch_id"] == "B1")["outcome"]
    text = (f"B1 keeps {b1['power_kwh']} kWh after {p['horizon_ticks']} ticks with "
            f"{b1['brownouts']} brownouts; B3 was rejected (grounding 0.258, 26%).")
    assert unsupported_claims(text, p) == []


def test_invented_number_and_branch_are_flagged():
    p = _packet()
    bad = unsupported_claims("B1 saves 73.4 kWh and B7 would have saved the crew.", p)
    assert "73.4" in bad and "branch B7" in bad


def test_packet_identifies_committed_branch_by_action():
    assert _packet()["committed_branch_id"] == "B1"

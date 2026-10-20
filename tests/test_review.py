"""REVIEW verdicts need an explicit human approval; DENY can never be approved.

Uses the labelled TEST DOUBLE from test_mission (no model)."""

import pytest
from test_mission import mission, prop

MID = lambda s: 0.55 if "activate_backup_power" in s.split("PROPOSED ACTION:")[1] else 0.2  # noqa: E731


def _decided():
    m, _ = mission(grounded=MID)
    props = [prop(m, "activate_backup_power"),
             prop(m, "isolate_module", {"module_id": "HAB"}, refs=("R-HAB-01",))]
    return m, m.decide(props)


def test_review_requested_instead_of_commit():
    m, out = _decided()
    assert out["committed"] is None and out["review"] == ["B1"]
    assert m.state.revision == 0
    assert m.events[-1].type == "review.requested"


def test_commit_of_review_without_approval_is_refused():
    m, out = _decided()
    p = m.fork_proposals[out["fork_id"]]["B1"]
    with pytest.raises(PermissionError):
        m.commit(p, m.cached_decision(out["fork_id"], p))


def test_operator_approval_commits_and_is_recorded():
    m, out = _decided()
    m.resolve_review(out["fork_id"], "B1", "cmdr-okafor", approve=True)
    assert m.state.backup_active and m.state.revision == 1
    ev = m.events[-1]
    assert ev.type == "action.committed" and ev.payload["approved_by"] == "cmdr-okafor"
    assert ev.payload["gate_verdict"] == "REVIEW"


def test_operator_rejection_leaves_state_unchanged():
    m, out = _decided()
    assert m.resolve_review(out["fork_id"], "B1", "op", approve=False) is None
    assert m.state.revision == 0 and m.events[-1].type == "review.rejected"


def test_denied_branch_cannot_be_approved():
    m, out = _decided()
    with pytest.raises(PermissionError):
        m.resolve_review(out["fork_id"], "B2", "op", approve=True)

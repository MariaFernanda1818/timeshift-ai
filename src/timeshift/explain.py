"""Consequence explanations grounded in a structured evidence packet.

Bedrock writes the operator-facing explanation from a packet of simulator outputs and gate
decisions. A deterministic check then extracts every number in the explanation and requires it
to appear in the packet (after rounding). Explanations that cite unknown numbers or branch IDs
are rejected and replaced by an explicit "insufficient grounding" notice, never silently shown.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from .mission import Mission

NUM = re.compile(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?")
BRANCH = re.compile(r"\bB\d\b")


class RejectedBranch(BaseModel):
    branch_id: str
    reason: str


class ConsequenceExplanation(BaseModel):
    headline: str = Field(description="One sentence, <= 20 words.")
    selected_branch: str | None = Field(description="Committed branch id, or null if none.")
    why_selected: str = Field(description="<= 50 words, citing numbers from the packet only.")
    rejected: list[RejectedBranch] = Field(default_factory=list)
    limitations: str = Field(description="What the simulation/evidence cannot tell us.")


def evidence_packet(m: Mission, fork_id: str) -> dict[str, Any]:
    fr = m.forks[fork_id]
    decisions = {d["action"]: d for d in m.decisions if d["fork_id"] == fork_id}
    branches = []
    for b in fr.branches:
        d = decisions.get(b.action.key()) if b.action else None
        o = b.outcome
        branches.append({
            "branch_id": b.branch_id, "action": b.label, "legal": b.legal,
            "violations": list(b.violations),
            "outcome": None if o is None else {
                "score": round(o.score, 3), "crew_alive": o.crew_alive, "crew_total": o.crew_total,
                "oxygen_kg": round(o.oxygen_kg, 1), "power_kwh": round(o.power_kwh, 1),
                "min_power_kwh": round(o.min_power_kwh, 1),
                "peak_reactor_c": round(o.peak_reactor_temp_c), "brownouts": o.brownout_events},
            "gate": None if d is None else {
                "verdict": d["verdict"],
                "evidence_grounded": (d["answers"].get("evidence_grounded") or {}).get("value"),
                "cited_evidence": d["proposal"]["cited_evidence"],
                "untrusted_cited": d["untrusted_evidence_refs"]},
        })
    committed = [p for _, p, _ in m.committed]
    # Match by action key: the commit tool builds its own Proposal (new id) for the same action.
    by_key = {b.action.key(): b.branch_id for b in fr.branches if b.action is not None}
    committed_branch = next((by_key[k] for t, _, k in m.committed
                             if t >= fr.origin_tick and k in by_key), None)
    return {"fork_id": fork_id, "horizon_ticks": fr.horizon, "tick_minutes": 5,
            "horizon_minutes": fr.horizon * 5,
            "origin_tick": fr.origin_tick, "branches": branches,
            "ranked_by_simulated_score": [b.branch_id for b in fr.ranked()],
            "committed_proposal_ids": committed, "committed_branch_id": committed_branch}


def _allowed_numbers(packet: dict[str, Any]) -> set[float]:
    vals: set[float] = set()

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.add(float(x))
            for nd in (0, 1, 2, 3):
                vals.add(round(float(x), nd))
            vals.add(round(float(x) * 100))           # 0.258 -> 26 (%)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            for n in NUM.findall(x):
                vals.add(float(n))
    walk(packet)
    return vals


def consistency_issues(exp: ConsequenceExplanation, packet: dict[str, Any]) -> list[str]:
    """Structural claims that must match the decision record exactly."""
    issues = []
    committed = packet.get("committed_branch_id")
    if exp.selected_branch != committed:
        issues.append(f"selected_branch {exp.selected_branch} but committed {committed}")
    ids = {b["branch_id"] for b in packet["branches"]}
    for r in exp.rejected:
        if r.branch_id == committed:
            issues.append(f"{r.branch_id} listed as rejected but it was committed")
        if r.branch_id not in ids:
            issues.append(f"rejected branch {r.branch_id} does not exist")
    return issues


def unsupported_claims(text: str, packet: dict[str, Any]) -> list[str]:
    """Numbers and branch ids in `text` that the packet does not contain."""
    allowed = _allowed_numbers(packet)
    ids = {b["branch_id"] for b in packet["branches"]}
    bad = [n for n in NUM.findall(BRANCH.sub("", text)) if float(n) not in allowed]
    bad += [f"branch {b}" for b in BRANCH.findall(text) if b not in ids]
    return bad


EXPLAIN_PROMPT = """Write an operator briefing about this counterfactual decision.
`selected_branch` MUST equal `committed_branch_id` from the packet (null if nothing was committed).
Use ONLY facts and numbers present in the JSON packet. Cite branch IDs. If the packet does not
support a statement, do not make it; say what is unknown in `limitations`.

PACKET:
{packet}"""


def explain(m: Mission, fork_id: str, model: Any) -> dict[str, Any]:
    """Ask Bedrock (via Strands structured output) and verify the result deterministically."""
    from strands import Agent

    packet = evidence_packet(m, fork_id)
    agent = Agent(model=model, callback_handler=None,
                  system_prompt="You explain simulated mission decisions precisely and briefly.")
    exp = agent.structured_output(ConsequenceExplanation,
                                  EXPLAIN_PROMPT.format(packet=json.dumps(packet, indent=1)))
    text = " ".join([exp.headline, exp.why_selected, exp.limitations]
                    + [f"{r.branch_id} {r.reason}" for r in exp.rejected])
    bad = unsupported_claims(text, packet) + consistency_issues(exp, packet)
    out = {"explanation": exp.model_dump(), "unsupported_claims": bad, "grounded": not bad,
           "packet": packet}
    m.emit("agent.explanation", out)
    return out

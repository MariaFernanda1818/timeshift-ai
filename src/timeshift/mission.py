"""Mission orchestrator: the ONLY component allowed to mutate canonical mission state.

Bedrock proposes. Simulation explores. Decider evaluates. Deterministic policies enforce.

Every mutation goes through `commit()`, which re-runs the deterministic policy at commit
time (so a decision taken against an older revision can never be applied) and requires a
PROCEED decision from the Counterfactual Decision Gate.
"""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from counterfactual_decision_gate import (
    CounterfactualBranch,
    CounterfactualDecisionGate,
    EvidenceItem,
    GateDecision,
    GateRequest,
    Verdict,
)
from pydantic import BaseModel, Field

from .sim.actions import ACTION_SCHEMAS, Action, apply_action, validate_action
from .sim.evidence import Observation, observe
from .sim.fork import Branch, ForkResult, fork_reality
from .sim.model import MissionState
from .sim.physics import simulate
from .sim.scenarios import Scenario, load_scenario

MAX_EVIDENCE_AGE_TICKS = 3
REPEAT_WINDOW_TICKS = 6


class Proposal(BaseModel):
    """A candidate action as proposed by the agent (LLM output, untrusted until checked)."""

    proposal_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    cited_evidence: list[str] = Field(default_factory=list)
    based_on_revision: int
    based_on_tick: int
    proposer: str = "agent"

    def action(self) -> Action:
        return Action(self.tool, dict(self.args))


class Event(BaseModel):
    """Single event format shared by the live stream and recorded replays."""

    seq: int
    ts: float
    mission_id: str
    tick: int
    revision: int
    type: str
    payload: dict[str, Any]


class Mission:
    def __init__(self, scenario: Scenario, gate: CounterfactualDecisionGate | None = None,
                 horizon: int = 20) -> None:
        self.scenario = scenario
        self.state: MissionState = scenario.state
        self.gate = gate
        self.horizon = horizon
        self.history: list[MissionState] = [self.state]
        self.forks: dict[str, ForkResult] = {}
        self.fork_proposals: dict[str, dict[str, Proposal]] = {}
        self.screened: dict[tuple[str, str, int], GateDecision] = {}
        self.decisions: list[dict[str, Any]] = []
        self.committed: list[tuple[int, str, str]] = []  # (tick, proposal_id, action key)
        self.events: list[Event] = []
        self._seq = itertools.count()
        self._lock = threading.RLock()
        self.listeners: list[Callable[[Event], None]] = []
        self.emit("mission.started", {"scenario": scenario.scenario_id, "title": scenario.title,
                                      "briefing": scenario.briefing,
                                      "seed": self.state.seed,
                                      "sim_version": self.state.sim_version,
                                      "state": self.snapshot()})

    @classmethod
    def from_scenario(cls, scenario_id: str, seed: int | None = None,
                      gate: CounterfactualDecisionGate | None = None) -> Mission:
        return cls(load_scenario(scenario_id, seed), gate)

    # ---- events ----------------------------------------------------------

    def emit(self, type_: str, payload: dict[str, Any]) -> Event:
        ev = Event(seq=next(self._seq), ts=time.time(), mission_id=self.state.mission_id,
                   tick=self.state.tick, revision=self.state.revision, type=type_,
                   payload=payload)
        self.events.append(ev)
        for listener in list(self.listeners):
            listener(ev)
        return ev

    def snapshot(self, s: MissionState | None = None) -> dict[str, Any]:
        s = s or self.state
        d = s.to_dict()
        d["state_hash"] = s.state_hash()
        return d

    def external_proposals(self) -> list[Proposal]:
        """Recommendations submitted by automated subsystems (e.g. an anomaly classifier).

        They enter the fork like any candidate and face the same gate; they are never trusted."""
        out = []
        for r in self.scenario.reports:
            if r.recommends is None:
                continue
            tool, args = r.recommends
            out.append(Proposal(tool=tool, args=dict(args), rationale=r.recommendation_rationale,
                                cited_evidence=[r.report_id], based_on_revision=self.state.revision,
                                based_on_tick=self.state.tick, proposer=r.source))
        return out

    # ---- observation -----------------------------------------------------

    def observations(self) -> list[Observation]:
        return observe(self.state, self.scenario.reports)

    def evidence_index(self) -> dict[str, Observation]:
        """All evidence ever observed this mission, by ID (older ticks included)."""
        idx: dict[str, Observation] = {}
        for s in self.history:
            for o in observe(s, self.scenario.reports):
                idx.setdefault(o.evidence_id, o)
        return idx

    # ---- time ------------------------------------------------------------

    def advance(self, ticks: int = 1) -> MissionState:
        with self._lock:
            for s in simulate(self.state, ticks):
                self.state = s
                self.history.append(s)
            self.emit("mission.advanced", {"ticks": ticks, "state": self.snapshot()})
            return self.state

    # ---- deterministic policy -------------------------------------------

    def policy_violations(self, p: Proposal) -> list[str]:
        """Mandatory invariants. Never delegated to a model."""
        s = self.state
        out: list[str] = []
        if p.tool not in ACTION_SCHEMAS:
            return [f"tool '{p.tool}' is not on the allowlist"]
        out += validate_action(s, p.action())
        # Temporal consistency: decisions must be taken against the live revision.
        if p.based_on_revision != s.revision:
            out.append(f"STALE: proposal based on revision {p.based_on_revision}, "
                       f"canonical revision is {s.revision}")
        if s.tick - p.based_on_tick > MAX_EVIDENCE_AGE_TICKS:
            out.append(f"STALE: proposal based on tick {p.based_on_tick}, now tick {s.tick} "
                       f"(max age {MAX_EVIDENCE_AGE_TICKS})")
        idx = self.evidence_index()
        for ref in p.cited_evidence:
            o = idx.get(ref)
            if o is None:
                out.append(f"cited evidence '{ref}' does not exist")
            elif o.trusted and s.tick - o.tick > MAX_EVIDENCE_AGE_TICKS:
                out.append(f"STALE: cited evidence {ref} is from tick {o.tick}, now tick {s.tick}")
        if any(pid == p.proposal_id for _, pid, _ in self.committed):
            out.append(f"proposal {p.proposal_id} was already committed (idempotency)")
        key = p.action().key()
        if any(k == key and s.tick - t < REPEAT_WINDOW_TICKS for t, _, k in self.committed):
            out.append(f"repeated action {key} within {REPEAT_WINDOW_TICKS} ticks")
        return out

    # ---- counterfactual exploration -------------------------------------

    def fork(self, proposals: list[Proposal]) -> tuple[str, ForkResult]:
        with self._lock:
            result = fork_reality(self.state, [p.action() for p in proposals],
                                  horizon=self.horizon)
            fork_id = f"F{len(self.forks) + 1:02d}"
            self.forks[fork_id] = result
            self.fork_proposals[fork_id] = {
                f"B{i}": p for i, p in enumerate(proposals, start=1)}
            self.emit("fork.created", {"fork_id": fork_id, **fork_payload(result, proposals)})
            return fork_id, result

    def gate_request(self, p: Proposal, fork_id: str | None) -> GateRequest:
        evidence = [EvidenceItem(evidence_id=o.evidence_id, text=o.text, trusted=o.trusted,
                                 source=o.source, observed_at=o.tick)
                    for o in self.observations()]
        # Evidence the agent cited from older ticks is shown too, labelled with its tick.
        idx = self.evidence_index()
        current = {e.evidence_id for e in evidence}
        for ref in p.cited_evidence:
            if ref not in current and ref in idx:
                o = idx[ref]
                evidence.append(EvidenceItem(evidence_id=o.evidence_id, text=o.text,
                                             trusted=o.trusted, source=o.source,
                                             observed_at=o.tick))
        proposed, alternatives = None, []
        if fork_id and fork_id in self.forks:
            for b in self.forks[fork_id].branches:
                cb = branch_summary(b)
                if b.action == p.action():
                    proposed = cb
                else:
                    alternatives.append(cb)
        return GateRequest(
            action_name=p.tool, action_args=p.args, rationale=p.rationale,
            cited_evidence=p.cited_evidence,
            situation=f"{self.scenario.title}. {self.scenario.briefing} "
                      f"Current tick {self.state.tick} (1 tick = 5 min).",
            evidence=evidence, proposed_branch=proposed, alternatives=alternatives,
            context_id=self.state.mission_id, state_revision=self.state.revision)

    def evaluate(self, p: Proposal, fork_id: str | None = None) -> GateDecision:
        if self.gate is None:
            raise RuntimeError("no decision gate configured; refusing to evaluate")
        violations = self.policy_violations(p)
        req = self.gate_request(p, fork_id)
        decision = self.gate.evaluate(req, extra_violations=violations)
        self.record_decision(p, fork_id, decision)
        return decision

    def record_decision(self, p: Proposal, fork_id: str | None, decision: GateDecision
                        ) -> dict[str, Any]:
        record = decision_record(self, p, fork_id, decision)
        self.decisions.append(record)
        self.emit("gate.decision", record)
        return record

    def screen(self, fork_id: str) -> dict[str, GateDecision]:
        """Gate EVERY candidate branch of a fork before anyone chooses one.

        Decisions are bound to the current revision; `cached_decision` will not reuse them
        once the canonical state has changed."""
        out: dict[str, GateDecision] = {}
        for p in self.fork_proposals.get(fork_id, {}).values():
            d = self.evaluate(p, fork_id)
            out[p.action().key()] = d
            self.screened[(fork_id, p.action().key(), self.state.revision)] = d
        self.emit("fork.screened", {"fork_id": fork_id,
                                    "verdicts": {k: d.verdict.value for k, d in out.items()}})
        return out

    def cached_decision(self, fork_id: str | None, p: Proposal) -> GateDecision | None:
        if fork_id is None:
            return None
        return self.screened.get((fork_id, p.action().key(), self.state.revision))

    # ---- the only mutation path -----------------------------------------

    def commit(self, p: Proposal, decision: GateDecision, approved_by: str | None = None
               ) -> MissionState:
        """Apply exactly one action. Requires PROCEED, or REVIEW plus an explicit human approval."""
        with self._lock:
            human_ok = decision.verdict == Verdict.REVIEW and bool(approved_by)
            if decision.verdict != Verdict.PROCEED and not human_ok:
                self.emit("action.rejected", {"proposal": p.model_dump(),
                                              "verdict": decision.verdict.value,
                                              "reasons": decision.reasons})
                raise PermissionError(f"gate verdict {decision.verdict.value}: "
                                      + "; ".join(decision.reasons))
            violations = self.policy_violations(p)  # re-check at commit time (TOCTOU)
            if violations:
                self.emit("action.rejected", {"proposal": p.model_dump(), "verdict": "DENY",
                                              "reasons": violations})
                raise PermissionError("; ".join(violations))
            new = apply_action(self.state, p.action())
            new = replace(new, revision=new.revision + 1)
            self.committed.append((self.state.tick, p.proposal_id, p.action().key()))
            self.state = new
            self.history.append(new)
            self.emit("action.committed", {"proposal": p.model_dump(),
                                           "gate_verdict": decision.verdict.value,
                                           "approved_by": approved_by,
                                           "state": self.snapshot()})
            return new

    # ---- human review (Strands `Confirm` equivalent for the orchestrated path) ----

    def pending_reviews(self, fork_id: str) -> list[str]:
        out = []
        for bid, p in self.fork_proposals.get(fork_id, {}).items():
            d = self.cached_decision(fork_id, p)
            if d is not None and d.verdict == Verdict.REVIEW:
                out.append(bid)
        return out

    def resolve_review(self, fork_id: str, branch_id: str, operator: str, approve: bool
                       ) -> MissionState | None:
        p = self.fork_proposals.get(fork_id, {}).get(branch_id)
        d = self.cached_decision(fork_id, p) if p else None
        if p is None or d is None or d.verdict != Verdict.REVIEW:
            raise PermissionError(f"{branch_id} has no pending REVIEW decision at this revision")
        if not approve:
            self.emit("review.rejected", {"fork_id": fork_id, "branch_id": branch_id,
                                          "operator": operator})
            return None
        self.emit("review.approved", {"fork_id": fork_id, "branch_id": branch_id,
                                      "operator": operator})
        return self.commit(p, d, approved_by=operator)

    # ---- one full deterministic cycle (used by benchmark & autopilot) ----

    def decide(self, proposals: list[Proposal]) -> dict[str, Any]:
        """Fork, gate EVERY branch, then commit the highest-scoring PROCEED branch.

        Abstains (commits nothing) if no candidate is approved."""
        fork_id, result = self.fork(proposals)
        screened = self.screen(fork_id)
        by_key = {p.action().key(): p for p in proposals}
        tried = [{"branch_id": b.branch_id, "verdict": screened[b.action.key()].verdict.value}
                 for b in result.branches if b.action is not None]
        for b in result.ranked():
            assert b.action is not None
            d = screened[b.action.key()]
            if d.verdict == Verdict.PROCEED:
                self.commit(by_key[b.action.key()], d)
                return {"fork_id": fork_id, "committed": b.branch_id, "tried": tried}
        review = self.pending_reviews(fork_id)
        if review:
            self.emit("review.requested", {"fork_id": fork_id, "branches": review})
            return {"fork_id": fork_id, "committed": None, "tried": tried, "review": review}
        self.emit("mission.abstained", {"fork_id": fork_id, "tried": tried})
        return {"fork_id": fork_id, "committed": None, "tried": tried}


# ---- serialisation helpers ------------------------------------------------

def branch_summary(b: Branch) -> CounterfactualBranch:
    if not b.legal or b.outcome is None:
        return CounterfactualBranch(branch_id=b.branch_id, action=b.label, legal=False,
                                    summary="ILLEGAL: " + "; ".join(b.violations))
    o = b.outcome
    summary = (f"after {len(b.trajectory)} ticks: crew alive {o.crew_alive}/{o.crew_total}, "
               f"O2 {o.oxygen_kg:.1f} kg, power reserve {o.power_kwh:.1f} kWh "
               f"(min {o.min_power_kwh:.1f}), reactor peak {o.peak_reactor_temp_c:.0f} C "
               f"{'online' if o.reactor_online else 'OFFLINE'}, brownouts {o.brownout_events}, "
               f"score {o.score:.3f}")
    return CounterfactualBranch(branch_id=b.branch_id, action=b.label, score=o.score,
                                summary=summary)


def fork_payload(result: ForkResult, proposals: list[Proposal] | None = None
                 ) -> dict[str, Any]:
    branches = []
    for i, b in enumerate(result.branches):
        p = proposals[i - 1] if proposals and i > 0 else None
        series = [{"tick": s.tick, "oxygen_kg": round(s.oxygen_reserve_kg, 2),
                   "power_kwh": round(s.power_reserve_kwh, 2),
                   "reactor_c": round(s.reactor_temp_c, 1),
                   "crew_health": round(sum(c.health_pct for c in s.crew) / len(s.crew), 1)}
                  for s in b.trajectory]
        branches.append({
            "branch_id": b.branch_id, "label": b.label,
            "action": None if b.action is None else {"tool": b.action.tool,
                                                     "args": b.action.args},
            "proposal_id": p.proposal_id if p else None,
            "proposer": p.proposer if p else None,
            "rationale": p.rationale if p else "",
            "cited_evidence": p.cited_evidence if p else [],
            "legal": b.legal, "violations": list(b.violations),
            "outcome": None if b.outcome is None else b.outcome.__dict__,
            "series": series, "events": list(b.events),
            "final_state": None if not b.trajectory else b.trajectory[-1].to_dict(),
        })
    return {"origin_tick": result.origin_tick, "origin_revision": result.origin_revision,
            "origin_hash": result.origin_hash, "seed": result.seed, "horizon": result.horizon,
            "sim_version": result.sim_version, "weights": result.weights.__dict__,
            "ranked": [b.branch_id for b in result.ranked()], "branches": branches}


def decision_record(m: Mission, p: Proposal, fork_id: str | None, d: GateDecision
                    ) -> dict[str, Any]:
    return {
        "mission_id": m.state.mission_id, "tick": m.state.tick, "revision": m.state.revision,
        "state_hash": m.state.state_hash(), "fork_id": fork_id,
        "proposal": p.model_dump(), "action": p.action().key(),
        "trusted_evidence_refs": [e for e in p.cited_evidence
                                  if (o := m.evidence_index().get(e)) and o.trusted],
        "untrusted_evidence_refs": [e for e in p.cited_evidence
                                    if (o := m.evidence_index().get(e)) and not o.trusted],
        "decider_model": d.decider_model, "decider_checkpoint": d.decider_checkpoint,
        "decider_status": d.decider_status,
        "questions": d.questions,
        "answers": {k: v.model_dump() for k, v in d.answers.items()},
        "thresholds": d.thresholds.model_dump(),
        "hard_violations": d.hard_violations,
        "verdict": d.verdict.value, "reasons": d.reasons, "escalation": d.escalation,
        "decider_latency_ms": d.decider_latency_ms, "decider_input_tokens":
            d.decider_input_tokens, "wall_latency_ms": d.wall_latency_ms,
        "state_text": d.state_text,
    }

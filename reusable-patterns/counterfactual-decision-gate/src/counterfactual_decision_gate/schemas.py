"""Data schemas for the Counterfactual Decision Gate. Application-agnostic."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    PROCEED = "PROCEED"   # commit the action
    REVIEW = "REVIEW"     # a human must confirm
    DENY = "DENY"         # do not commit; send the agent back with the reason


class EvidenceItem(BaseModel):
    """One observation the agent may cite. Only `trusted=True` items count as grounding."""

    evidence_id: str
    text: str
    trusted: bool = True
    source: str = "telemetry"
    observed_at: int | None = None       # logical clock (tick, sequence number, ...)


class CounterfactualBranch(BaseModel):
    """A simulated future for one candidate. Numbers come from the simulator, never the LLM."""

    branch_id: str
    action: str
    score: float | None = None
    summary: str                          # concise, simulator-derived description
    legal: bool = True


class GateRequest(BaseModel):
    """Everything the gate needs to judge one proposed action."""

    action_name: str
    action_args: dict[str, Any]
    rationale: str = ""
    cited_evidence: list[str] = Field(default_factory=list)
    situation: str                        # the incident / task description
    evidence: list[EvidenceItem]
    proposed_branch: CounterfactualBranch | None = None
    alternatives: list[CounterfactualBranch] = Field(default_factory=list)
    context_id: str = ""                  # mission / ticket / workflow id
    state_revision: int | None = None


class Thresholds(BaseModel):
    """Policy knobs over Decider probabilities. Owned by the code, not the model.

    PROCEED requires grounding >= proceed_at AND the verdict question not choosing `deny`.
    DENY when grounding < deny_below OR the verdict question chooses `deny` with
    confidence >= verdict_deny_conf. Everything in between is REVIEW."""

    proceed_at: float = 0.70
    deny_below: float = 0.40
    verdict_deny_conf: float = 0.60
    # Optional extra noul questions: name -> minimum P(true); below it the verdict is REVIEW.
    secondary_min: dict[str, float] = Field(default_factory=dict)


class QuestionAnswer(BaseModel):
    name: str
    type: str
    value: float | str
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


class GateDecision(BaseModel):
    """Auditable record of one gate evaluation."""

    verdict: Verdict
    reasons: list[str]
    hard_violations: list[str] = Field(default_factory=list)
    answers: dict[str, QuestionAnswer] = Field(default_factory=dict)
    decider_model: str | None = None
    decider_checkpoint: str | None = None
    decider_latency_ms: float | None = None
    decider_input_tokens: int | None = None
    wall_latency_ms: float | None = None
    decider_status: str = "ok"            # ok | unavailable | timeout | malformed | skipped
    # Optional second opinion for the REVIEW band only (see CounterfactualDecisionGate.escalate).
    escalation: dict[str, Any] | None = None
    thresholds: Thresholds = Field(default_factory=Thresholds)
    questions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state_text: str = ""
    request: GateRequest | None = None

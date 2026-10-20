"""Counterfactual Decision Gate: a reusable Strands Decider 2B guardrail pattern.

Gate a consequential agent action on (1) deterministic hard checks and (2) a typed
Decider 2B judgement of whether the action is grounded in trusted evidence and in the
simulated (counterfactual) outcomes of the alternatives.
"""

from .client import (
    DeciderClient,
    DeciderError,
    DeciderMalformedResponse,
    DeciderTimeout,
    DeciderUnavailable,
    DeciderVersionMismatch,
)
from .gate import CounterfactualDecisionGate
from .questions import (
    ADDRESSES_SITUATION,
    DEFAULT_QUESTIONS,
    EVIDENCE_GROUNDED,
    EXTENDED_QUESTIONS,
    VERDICT,
    render_state,
)
from .schemas import (
    CounterfactualBranch,
    EvidenceItem,
    GateDecision,
    GateRequest,
    QuestionAnswer,
    Thresholds,
    Verdict,
)

__all__ = [
    "ADDRESSES_SITUATION", "DEFAULT_QUESTIONS", "EXTENDED_QUESTIONS", "EVIDENCE_GROUNDED", "VERDICT", "CounterfactualBranch",
    "CounterfactualDecisionGate", "DeciderClient", "DeciderError", "DeciderMalformedResponse",
    "DeciderTimeout", "DeciderUnavailable", "DeciderVersionMismatch", "EvidenceItem",
    "GateDecision", "GateRequest", "QuestionAnswer", "Thresholds", "Verdict", "render_state",
]

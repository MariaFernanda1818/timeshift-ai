"""The Counterfactual Decision Gate.

Responsibilities are deliberately separated:

* deterministic `hard_checks` (supplied by the application) enforce mandatory invariants;
  a hard violation is a DENY no matter what Decider says;
* Strands Decider 2B answers typed semantic questions about evidence grounding;
* `Thresholds` turn Decider's probabilities into PROCEED / REVIEW / DENY in plain code.

Any Decider failure (unreachable, timeout, malformed answer, checkpoint mismatch) is
fail-closed: the verdict is DENY with `decider_status` set, and nothing is committed.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from .client import DeciderClient, DeciderError
from .questions import DEFAULT_QUESTIONS, render_state
from .schemas import GateDecision, GateRequest, QuestionAnswer, Thresholds, Verdict

HardChecks = Callable[[GateRequest], list[str]]


class CounterfactualDecisionGate:
    def __init__(
        self,
        client: DeciderClient,
        thresholds: Thresholds | None = None,
        questions: Mapping[str, dict[str, Any]] | None = None,
        hard_checks: HardChecks | None = None,
        ask_on_hard_violation: bool = False,
    ) -> None:
        self.client = client
        self.thresholds = thresholds or Thresholds()
        self.questions = dict(questions or DEFAULT_QUESTIONS)
        if "evidence_grounded" not in self.questions:
            raise ValueError("questions must include 'evidence_grounded'")
        self.hard_checks = hard_checks
        self.ask_on_hard_violation = ask_on_hard_violation

    def evaluate(self, req: GateRequest, extra_violations: list[str] | None = None
                 ) -> GateDecision:
        """`extra_violations` lets a caller pass deterministic violations it already computed."""
        t0 = time.perf_counter()
        hard = list(self.hard_checks(req)) if self.hard_checks else []
        hard += list(extra_violations or [])
        state = render_state(req)
        base = {"thresholds": self.thresholds, "questions": self.questions, "state_text": state,
                "request": req, "hard_violations": hard}

        if hard and not self.ask_on_hard_violation:
            return GateDecision(
                verdict=Verdict.DENY, decider_status="skipped",
                reasons=[f"deterministic policy: {v}" for v in hard],
                wall_latency_ms=_ms(t0), **base)

        try:
            health = self.client.health()
            payload = self.client.ask(state, self.questions)
        except DeciderError as exc:
            return GateDecision(
                verdict=Verdict.DENY, decider_status=exc.status,
                reasons=[f"Decider {exc.status}: {exc} -- failing closed, no action committed"]
                + [f"deterministic policy: {v}" for v in hard],
                wall_latency_ms=_ms(t0), **base)

        answers = _parse_answers(payload["answers"], self.questions)
        verdict, reasons = self.apply_policy(answers)
        if hard:
            verdict = Verdict.DENY
            reasons = [f"deterministic policy: {v}" for v in hard] + [
                "Decider answers recorded for audit only; deterministic policy is authoritative"]
        return GateDecision(
            verdict=verdict, reasons=reasons, answers=answers,
            decider_model=payload.get("model"), decider_checkpoint=health.get("checkpoint"),
            decider_latency_ms=payload.get("latency_ms"),
            decider_input_tokens=(payload.get("usage") or {}).get("input_tokens"),
            wall_latency_ms=_ms(t0), **base)

    def apply_policy(self, answers: Mapping[str, QuestionAnswer]) -> tuple[Verdict, list[str]]:
        th = self.thresholds
        grounded = float(answers["evidence_grounded"].value)
        v = answers.get("verdict")
        reasons: list[str] = []
        if grounded < th.deny_below:
            reasons.append(f"evidence_grounded={grounded:.2f} < deny_below={th.deny_below}")
            return Verdict.DENY, reasons
        if v is not None and v.value == "deny" and (v.confidence or 0) >= th.verdict_deny_conf:
            reasons.append(f"verdict=deny with confidence {v.confidence:.2f} >= "
                           f"{th.verdict_deny_conf}")
            return Verdict.DENY, reasons
        for name, minimum in th.secondary_min.items():
            a = answers.get(name)
            if a is not None and float(a.value) < minimum:
                reasons.append(f"{name}={float(a.value):.2f} < {minimum}")
                return Verdict.REVIEW, reasons
        if grounded >= th.proceed_at and (v is None or v.value != "deny"):
            reasons.append(f"evidence_grounded={grounded:.2f} >= proceed_at={th.proceed_at}")
            return Verdict.PROCEED, reasons
        reasons.append(f"evidence_grounded={grounded:.2f} is between deny_below={th.deny_below} "
                       f"and proceed_at={th.proceed_at}"
                       + (f"; verdict={v.value}" if v is not None else ""))
        return Verdict.REVIEW, reasons


def _parse_answers(raw: Mapping[str, Any], questions: Mapping[str, dict[str, Any]]
                   ) -> dict[str, QuestionAnswer]:
    out: dict[str, QuestionAnswer] = {}
    for name, q in questions.items():
        a = raw[name]
        kind = q["type"]
        if kind == "noul":
            p = float(a["noul"])
            out[name] = QuestionAnswer(name=name, type=kind, value=p,
                                       probabilities={"true": p, "false": 1 - p},
                                       confidence=max(p, 1 - p))
        elif kind == "choice":
            out[name] = QuestionAnswer(name=name, type=kind, value=a["choice"],
                                       probabilities=a.get("probabilities"),
                                       confidence=a.get("confidence"))
        else:
            out[name] = QuestionAnswer(name=name, type=kind, value=float(a[kind]),
                                       probabilities=a.get("probabilities"),
                                       confidence=a.get("confidence"))
    return out


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)

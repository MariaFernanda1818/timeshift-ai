"""Strands Agents integration: place the gate on the agent's tool-execution path.

`CounterfactualGateHandler` is an `InterventionHandler`. Strands calls `before_tool_call`
before any tool runs; for gated tools the handler builds a GateRequest (through an
application callback that runs the counterfactual simulation and gathers evidence),
evaluates it, and maps the verdict onto Strands' typed actions:

    PROCEED -> Proceed()
    DENY    -> Guide(feedback)  (default: the model gets the reason and picks another action)
               or Deny(reason)  (deny_mode="deny": hard stop)
    REVIEW  -> Confirm(prompt)  (default: pause for a human)
               or Deny(reason)  (review_mode="deny": unattended agents)

`on_error = "deny"` makes the handler fail closed if anything inside it raises.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from strands.interventions import Confirm, Deny, Guide, InterventionHandler, Proceed

from .gate import CounterfactualDecisionGate
from .schemas import GateDecision, GateRequest, Verdict

RequestBuilder = Callable[[str, dict[str, Any], Any], GateRequest]
PolicyCheck = Callable[[str, dict[str, Any], Any], list[str]]
CachedDecision = Callable[[str, dict[str, Any], Any], GateDecision | None]


class CounterfactualGateHandler(InterventionHandler):
    name = "counterfactual-decision-gate"

    def __init__(
        self,
        gate: CounterfactualDecisionGate,
        build_request: RequestBuilder,
        gated_tools: set[str],
        on_decision: Callable[[str, dict[str, Any], GateDecision], None] | None = None,
        policy_check: PolicyCheck | None = None,
        cached_decision: CachedDecision | None = None,
        deny_mode: Literal["guide", "deny"] = "guide",
        review_mode: Literal["confirm", "deny"] = "confirm",
        max_denials_per_tool: int = 3,
    ) -> None:
        self.gate = gate
        self.build_request = build_request
        self.gated_tools = set(gated_tools)
        self.on_decision = on_decision
        self.policy_check = policy_check
        self.cached_decision = cached_decision
        self.deny_mode = deny_mode
        self.review_mode = review_mode
        self.max_denials_per_tool = max_denials_per_tool
        self.decisions: list[GateDecision] = []
        self._denials: dict[str, int] = {}

    @property
    def on_error(self) -> Literal["deny"]:
        return "deny"

    def before_tool_call(self, event: Any, **kwargs: Any) -> Any:
        tool = event.tool_use["name"]
        if tool not in self.gated_tools:
            return Proceed(reason="tool not gated")
        args = dict(event.tool_use.get("input") or {})
        violations = self.policy_check(tool, args, event) if self.policy_check else []
        # Reuse a decision already made for this exact action (e.g. every forked branch was
        # screened up front), but only while the deterministic policy still passes right now.
        cached = self.cached_decision(tool, args, event) if self.cached_decision else None
        if cached is not None and not violations:
            decision = cached
        else:
            decision = self.gate.evaluate(self.build_request(tool, args, event),
                                          extra_violations=violations)
            if self.on_decision:
                self.on_decision(tool, args, decision)
        self.decisions.append(decision)
        reason = "; ".join(decision.reasons)

        if decision.verdict == Verdict.PROCEED:
            return Proceed(reason=reason)
        if decision.verdict == Verdict.REVIEW and self.review_mode == "confirm":
            return Confirm(prompt=f"Counterfactual gate requests human review of {tool}: {reason}",
                           reason=reason)
        # DENY (or REVIEW with review_mode="deny")
        self._denials[tool] = self._denials.get(tool, 0) + 1
        label = "denied" if decision.verdict == Verdict.DENY else "held for review"
        if self.deny_mode == "guide" and self._denials[tool] <= self.max_denials_per_tool:
            return Guide(feedback=(
                f"The proposed {tool} call was {label} by the counterfactual decision gate: "
                f"{reason}. Do not retry it unchanged. Choose an alternative that is supported "
                "by TRUSTED evidence, or explain that no supported action exists."), reason=reason)
        return Deny(reason=f"{tool} {label}: {reason}")

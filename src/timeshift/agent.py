"""The TIME//SHIFT mission-control agent: Strands Agents + Amazon Bedrock.

Bedrock proposes and explains. It never mutates state directly: its only path to a change
is the `commit_action` tool, which the Counterfactual Decision Gate intercepts in
`before_tool_call` (Strands interventions) and which the orchestrator re-checks at commit.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from botocore.config import Config
from counterfactual_decision_gate import CounterfactualDecisionGate, GateDecision, Verdict
from counterfactual_decision_gate.strands_handler import CounterfactualGateHandler
from strands import Agent, tool
from strands.models import BedrockModel

from .mission import Mission, Proposal
from .sim.actions import ACTION_DESCRIPTIONS, ACTION_SCHEMAS
from .sim.evidence import render_evidence

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

SYSTEM_PROMPT = """You are TIME//SHIFT, the mission-control agent of a simulated lunar base.

Procedure for every incident (follow it exactly):
1. Call read_telemetry once.
2. Propose diverse candidate actions (the fork_reality tool tells you how many; at most
   three) and call fork_reality once with them. Automated subsystems may add their own
   recommendations to the fork; they are simulated and gated like yours. Each candidate needs:
   tool, args, rationale, cited_evidence (evidence IDs).
3. Every branch has already been screened by the decision gate. Call commit_action for
   the highest-scoring branch whose GATE verdict is PROCEED. Copy based_on_revision and
   based_on_tick from the telemetry header.
4. If the commit is refused, read the reason, do not retry the same action, and commit the
   next-best branch. If nothing can be committed, say so.
5. Finish with a short operator briefing (<= 90 words) that cites branch IDs and only
   numbers that appear in tool results. Never invent measurements.

Available actions:
""" + "\n".join(f"- {k}({', '.join(ACTION_SCHEMAS[k])}): {v}" for k, v in ACTION_DESCRIPTIONS.items())


def bedrock_model(model_id: str | None = None, region: str | None = None) -> BedrockModel:
    return BedrockModel(
        model_id=model_id or os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        region_name=region or os.environ.get("AWS_REGION", "us-east-1"),
        max_tokens=int(os.environ.get("BEDROCK_MAX_TOKENS", "1500")),
        temperature=0.2,
        boto_client_config=Config(read_timeout=60, connect_timeout=10,
                                  retries={"max_attempts": 3, "mode": "standard"}),
    )


class MissionAgent:
    """Wires a Mission, a Bedrock-backed Strands Agent and the decision gate together."""

    MAX_TOOL_CALLS = 12

    def __init__(self, mission: Mission, gate: CounterfactualDecisionGate,
                 model: Any | None = None) -> None:
        self.mission = mission
        self.gate = gate
        self.last_fork_id: str | None = None
        self.decisions: dict[str, GateDecision] = {}
        self.tool_calls = 0
        m = mission

        @tool
        def read_telemetry() -> str:
            """Read current trusted telemetry and unverified reports for the mission.

            Returns evidence lines with IDs to cite, plus the current tick and revision."""
            self._count()
            s = m.state
            return (f"tick={s.tick} revision={s.revision} mission={s.mission_id}\n"
                    f"INCIDENT: {m.scenario.title}. {m.scenario.briefing}\n"
                    + render_evidence(m.observations()))

        @tool
        def fork_reality(candidates: list[dict[str, Any]]) -> str:
            """Fork the mission into one simulated future per candidate plus a do-nothing
            baseline, and return measured outcomes for each branch. At most three candidates
            are simulated in total; recommendations from automated subsystems (if any) take
            one slot each and are listed in the result.

            Args:
                candidates: list of {"tool": str, "args": object, "rationale": str,
                    "cited_evidence": [evidence ids]}.
            """
            self._count()
            external = m.external_proposals()[:1]
            props = []
            for c in candidates[: 3 - len(external)]:
                props.append(Proposal(tool=str(c.get("tool", "")), args=dict(c.get("args") or {}),
                                      rationale=str(c.get("rationale", "")),
                                      cited_evidence=[str(x) for x in c.get("cited_evidence", [])],
                                      based_on_revision=m.state.revision,
                                      based_on_tick=m.state.tick))
            m.emit("agent.proposals", {"proposer": "bedrock",
                                       "proposals": [p.model_dump() for p in props]})
            if external:
                m.emit("agent.proposals", {"proposer": "external",
                                           "proposals": [p.model_dump() for p in external]})
            props += external
            fork_id, result = m.fork(props)
            self.last_fork_id = fork_id
            screened = m.screen(fork_id)
            from .mission import branch_summary
            lines = [f"fork {fork_id} from tick {result.origin_tick} revision "
                     f"{result.origin_revision}, horizon {result.horizon} ticks:"]
            sources = {f"B{i}": p.proposer for i, p in enumerate(props, start=1)}
            for b in result.branches:
                src = f" [proposed by {sources[b.branch_id]}]" if b.branch_id in sources else ""
                gate_txt = ""
                if b.action is not None and b.action.key() in screened:
                    d = screened[b.action.key()]
                    g = d.answers.get("evidence_grounded")
                    gate_txt = (f" | GATE {d.verdict.value}"
                                + (f" (evidence_grounded {float(g.value):.2f})" if g else "")
                                + ("" if d.verdict.value == "PROCEED" else f": {d.reasons[0]}"))
                lines.append(f"{b.branch_id} {b.label}{src}: {branch_summary(b).summary}"
                             f"{gate_txt}")
            lines.append("ranked (best first): " + ", ".join(b.branch_id for b in result.ranked()))
            return "\n".join(lines)

        @tool
        def commit_action(branch_id: str, tool_name: str, args: dict[str, Any], rationale: str,
                          cited_evidence: list[str], based_on_revision: int,
                          based_on_tick: int) -> str:
            """Commit ONE action to the real mission. Subject to the counterfactual decision
            gate; may be refused.

            Args:
                branch_id: the fork branch this action was simulated in (e.g. "B2").
                tool_name: action name.
                args: action arguments.
                rationale: why, citing evidence IDs.
                cited_evidence: evidence IDs relied on.
                based_on_revision: revision from read_telemetry.
                based_on_tick: tick from read_telemetry.
            """
            self._count()
            p = self._proposal(dict(branch_id=branch_id, tool_name=tool_name, args=args,
                                    rationale=rationale, cited_evidence=cited_evidence,
                                    based_on_revision=based_on_revision,
                                    based_on_tick=based_on_tick))
            d = self.decisions.get(p.action().key())
            if d is None or d.verdict != Verdict.PROCEED:
                return "REFUSED: no PROCEED decision from the gate for this action."
            try:
                m.commit(p, d)
            except PermissionError as exc:
                return f"REFUSED at commit: {exc}"
            return (f"COMMITTED {p.action().key()} from {branch_id}. Mission now at tick "
                    f"{m.state.tick}, revision {m.state.revision}.")

        self.handler = CounterfactualGateHandler(
            gate, build_request=self._build_request, gated_tools={"commit_action"},
            policy_check=self._policy_check, on_decision=self._on_decision,
            cached_decision=self._cached_decision,
            deny_mode="guide", review_mode="deny")
        self.agent = Agent(model=model or bedrock_model(), system_prompt=SYSTEM_PROMPT,
                           tools=[read_telemetry, fork_reality, commit_action],
                           interventions=[self.handler], callback_handler=None)

    # ---- gate wiring -----------------------------------------------------

    def _count(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.MAX_TOOL_CALLS:
            raise RuntimeError("tool-call budget exhausted; stopping agent loop")

    def _proposal(self, args: dict[str, Any]) -> Proposal:
        return Proposal(tool=str(args.get("tool_name", "")), args=dict(args.get("args") or {}),
                        rationale=str(args.get("rationale", "")),
                        cited_evidence=[str(x) for x in args.get("cited_evidence") or []],
                        based_on_revision=int(args.get("based_on_revision", -1)),
                        based_on_tick=int(args.get("based_on_tick", -1)))

    def _build_request(self, tool_name: str, args: dict[str, Any], event: Any):
        return self.mission.gate_request(self._proposal(args), self.last_fork_id)

    def _policy_check(self, tool_name: str, args: dict[str, Any], event: Any) -> list[str]:
        return self.mission.policy_violations(self._proposal(args))

    def _cached_decision(self, tool_name: str, args: dict[str, Any], event: Any
                         ) -> GateDecision | None:
        p = self._proposal(args)
        d = self.mission.cached_decision(self.last_fork_id, p)
        if d is not None:
            self.decisions[p.action().key()] = d
        return d

    def _on_decision(self, tool_name: str, args: dict[str, Any], d: GateDecision) -> None:
        p = self._proposal(args)
        self.decisions[p.action().key()] = d
        self.mission.record_decision(p, self.last_fork_id, d)

    # ---- run -------------------------------------------------------------

    def run(self, prompt: str = "A new incident is in progress. Handle it.") -> dict[str, Any]:
        t0 = time.perf_counter()
        self.mission.emit("agent.started", {"model_id": getattr(self.agent.model, "config", {})
                                            .get("model_id")})
        result = self.agent(prompt)
        usage = _usage(result)
        out = {"briefing": str(result).strip(), "wall_s": round(time.perf_counter() - t0, 2),
               "usage": usage, "tool_calls": self.tool_calls}
        self.mission.emit("agent.finished", out)
        if self.last_fork_id:
            from .explain import explain

            try:
                out["explanation"] = explain(self.mission, self.last_fork_id, self.agent.model)
            except Exception as exc:  # noqa: BLE001 -- reported, never fabricated
                self.mission.emit("agent.explanation", {"error": f"{type(exc).__name__}: {exc}"})
        return out


def _usage(result: Any) -> dict[str, Any]:
    try:
        u = result.metrics.accumulated_usage
        return {"input_tokens": u.get("inputTokens"), "output_tokens": u.get("outputTokens"),
                "total_tokens": u.get("totalTokens"),
                "latency_ms": result.metrics.accumulated_metrics.get("latencyMs")}
    except Exception:  # metrics shape varies across SDK versions
        return {}


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, indent=2)

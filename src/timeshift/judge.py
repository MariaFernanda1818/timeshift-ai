"""Bedrock LLM judge: benchmark config B and the optional REVIEW-band second opinion.

Asks the SAME typed question as Decider (`EVIDENCE_GROUNDED`) and applies the SAME thresholds,
so the two are directly comparable. Used only (a) in the benchmark and (b) when explicitly
enabled as an escalation for Decider's review band. It never replaces a failed Decider.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from counterfactual_decision_gate import EVIDENCE_GROUNDED, GateRequest

LLM_JUDGE_PROMPT = """You are a strict evaluator. Read the STATE and answer the QUESTION.

QUESTION: {q}
"true" means: {t}
"false" means: {f}

Reply with ONLY a JSON object: {{"p_true": <probability between 0 and 1 that the answer is true>}}

STATE:
{state}"""


class BedrockJudge:
    def __init__(self, model_id: str | None = None, region: str | None = None) -> None:
        import boto3
        from botocore.config import Config

        self.model_id = model_id or os.environ.get(
            "JUDGE_MODEL_ID", os.environ.get("BEDROCK_MODEL_ID",
                                             "us.anthropic.claude-haiku-4-5-20251001-v1:0"))
        self.rt = boto3.client("bedrock-runtime",
                               region_name=region or os.environ.get("AWS_REGION", "us-east-1"),
                               config=Config(read_timeout=60,
                                             retries={"max_attempts": 10, "mode": "adaptive"}))

    def ask(self, state: str) -> dict[str, Any]:
        q = EVIDENCE_GROUNDED
        prompt = LLM_JUDGE_PROMPT.format(q=q["instructions"], t=q["criteria"]["true"],
                                         f=q["criteria"]["false"], state=state)
        t0 = time.perf_counter()
        r = self.rt.converse(modelId=self.model_id,
                             messages=[{"role": "user", "content": [{"text": prompt}]}],
                             inferenceConfig={"maxTokens": 60, "temperature": 0.0})
        ms = (time.perf_counter() - t0) * 1000
        text = r["output"]["message"]["content"][0]["text"]
        p = None
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                p = float(json.loads(m.group(0))["p_true"])
            except (ValueError, KeyError, TypeError):
                p = None
        if p is not None and not 0.0 <= p <= 1.0:
            p = None
        return {"p_true": p, "raw": text[:200], "latency_ms": round(ms, 1),
                "usage": r.get("usage", {}), "request_id": r["ResponseMetadata"]["RequestId"]}

    def escalation(self, proceed_at: float, deny_below: float):
        """Adapter for CounterfactualDecisionGate(escalate=...). A malformed answer keeps REVIEW."""

        def escalate(req: GateRequest, state: str) -> dict[str, Any]:
            out = self.ask(state)
            p = out["p_true"]
            verdict = ("REVIEW" if p is None else "PROCEED" if p >= proceed_at
                       else "DENY" if p < deny_below else "REVIEW")
            return {"verdict": verdict, "judge": self.model_id, **out}

        return escalate

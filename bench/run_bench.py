"""Benchmark: A (deterministic only) vs B (Bedrock LLM judge) vs C (Strands Decider 2B).

    python bench/run_bench.py --config C --split eval --out bench/results/C-eval.jsonl
    python bench/run_bench.py --config B --split eval --out bench/results/B-eval.jsonl
    python bench/run_bench.py --config A --split all  --out bench/results/A-all.jsonl

All configurations see identical cases, states, seeds, candidates, evidence rendering,
simulation horizon and thresholds. B and C use the same question text. Nothing is mocked:
C needs a running Decider server, B needs Bedrock credentials. Each line of the output
file is one measured case; summaries are computed by bench/summarize.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
from typing import Any

import psutil

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cases import CASES, Case  # noqa: E402
from counterfactual_decision_gate import (  # noqa: E402
    CounterfactualDecisionGate,
    DeciderClient,
    EVIDENCE_GROUNDED,
    Thresholds,
)
from counterfactual_decision_gate.gate import _parse_answers  # noqa: E402
from counterfactual_decision_gate.schemas import QuestionAnswer, Verdict  # noqa: E402
from timeshift.mission import Mission, Proposal  # noqa: E402

LLM_JUDGE_PROMPT = """You are a strict evaluator. Read the STATE and answer the QUESTION.

QUESTION: {q}
"true" means: {t}
"false" means: {f}

Reply with ONLY a JSON object: {{"p_true": <probability between 0 and 1 that the answer is true>}}

STATE:
{state}"""


def build(case: Case, gate: CounterfactualDecisionGate | None) -> tuple[Mission, Proposal, str]:
    m = Mission.from_scenario(case.scenario, case.seed, gate)
    if case.advance:
        m.advance(case.advance)
    based_tick = m.state.tick - case.stale_by
    t = f"E{based_tick:03d}"
    p = Proposal(tool=case.tool, args=case.args, rationale=case.rationale.replace("{t}", t),
                 cited_evidence=[c.replace("{t}", t) for c in case.cited],
                 based_on_revision=m.state.revision, based_on_tick=based_tick)
    fork_id, _ = m.fork([p])
    return m, p, fork_id


class BedrockJudge:
    """Config B: an ordinary LLM on Bedrock answers the SAME typed question."""

    def __init__(self, model_id: str, region: str) -> None:
        import boto3
        from botocore.config import Config

        self.model_id = model_id
        self.rt = boto3.client("bedrock-runtime", region_name=region,
                               config=Config(read_timeout=60, retries={"max_attempts": 10, "mode": "adaptive"}))

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
        mt = re.search(r"\{.*\}", text, re.S)
        p = None
        if mt:
            try:
                p = float(json.loads(mt.group(0))["p_true"])
            except (ValueError, KeyError, TypeError):
                p = None
        return {"p_true": p, "raw": text[:200], "latency_ms": round(ms, 1),
                "usage": r.get("usage", {}), "request_id": r["ResponseMetadata"]["RequestId"]}


def run_case(case: Case, config: str, gate, judge, thresholds: Thresholds) -> dict[str, Any]:
    proc = psutil.Process()
    m, p, fork_id = build(case, gate if config == "C" else None)
    violations = m.policy_violations(p)
    rec: dict[str, Any] = {"case_id": case.case_id, "split": case.split, "config": config,
                           "scenario": case.scenario, "category": case.category,
                           "should_commit": case.should_commit, "action": p.action().key(),
                           "deterministic_violations": violations}
    t0 = time.perf_counter()
    cpu0 = proc.cpu_times()
    if config == "A":
        verdict = "DENY" if violations else "PROCEED"
        rec.update(verdict=verdict, judge_latency_ms=0.0)
    elif config == "C":
        d = m.evaluate(p, fork_id)
        g = d.answers.get("evidence_grounded")
        v = d.answers.get("verdict")
        rec.update(verdict=d.verdict.value, decider_status=d.decider_status,
                   grounded=None if g is None else g.value,
                   verdict_choice=None if v is None else v.value,
                   verdict_probs=None if v is None else v.probabilities,
                   addresses=(d.answers["addresses_situation"].value
                              if "addresses_situation" in d.answers else None),
                   judge_latency_ms=d.decider_latency_ms, input_tokens=d.decider_input_tokens,
                   checkpoint=d.decider_checkpoint)
    else:  # B
        if violations:
            rec.update(verdict="DENY", judge_status="skipped", judge_latency_ms=0.0)
        else:
            from counterfactual_decision_gate.questions import render_state

            out = judge.ask(render_state(m.gate_request(p, fork_id)))
            if out["p_true"] is None or not 0 <= out["p_true"] <= 1:
                rec.update(verdict="DENY", judge_status="malformed", judge_raw=out["raw"])
            else:
                ans = {"evidence_grounded": QuestionAnswer(name="evidence_grounded", type="noul",
                                                           value=out["p_true"])}
                gate_b = CounterfactualDecisionGate(DeciderClient(url="http://unused.invalid"),
                                                    thresholds,
                                                    questions={"evidence_grounded":
                                                               EVIDENCE_GROUNDED})
                verdict, _ = gate_b.apply_policy(ans)
                rec.update(verdict=verdict.value, judge_status="ok", grounded=out["p_true"])
            rec.update(judge_latency_ms=out["latency_ms"], judge_model=judge.model_id,
                       input_tokens=out["usage"].get("inputTokens"),
                       output_tokens=out["usage"].get("outputTokens"),
                       request_id=out["request_id"])
    rec["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    cpu1 = proc.cpu_times()
    rec["client_cpu_s"] = round((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system), 3)
    committed = rec["verdict"] == "PROCEED"
    rec["committed"] = committed
    # Simulated consequence of the configuration's choice vs doing nothing (same horizon).
    fr = m.forks[fork_id]
    chosen = fr.branches[1] if committed and fr.branches[1].legal else fr.baseline()
    rec["sim_score"] = chosen.outcome.score if chosen.outcome else None
    rec["sim_crew_health"] = chosen.outcome.mean_crew_health_pct if chosen.outcome else None
    rec["sim_crew_alive"] = chosen.outcome.crew_alive if chosen.outcome else None
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=["A", "B", "C"], required=True)
    ap.add_argument("--split", choices=["calib", "eval", "all"], default="eval")
    ap.add_argument("--out", required=True)
    ap.add_argument("--proceed-at", type=float, default=0.70)
    ap.add_argument("--deny-below", type=float, default=0.40)
    ap.add_argument("--variant", default=None, choices=[None, "C2"],
                    help="C2: Decider with the extra addresses_situation question")
    ap.add_argument("--secondary-min", type=float, default=0.5)
    ap.add_argument("--pace-s", type=float, default=4.0,
                    help="config B: pause between Bedrock calls (new accounts are rate-limited)")
    a = ap.parse_args()
    th = Thresholds(proceed_at=a.proceed_at, deny_below=a.deny_below)
    cases = [c for c in CASES if a.split == "all" or c.split == a.split]
    gate = judge = None
    if a.config == "C":
        client = DeciderClient(timeout_s=900, retries=0)
        client.health()
        if a.variant == "C2":
            from counterfactual_decision_gate import EXTENDED_QUESTIONS

            th = Thresholds(proceed_at=a.proceed_at, deny_below=a.deny_below,
                            secondary_min={"addresses_situation": a.secondary_min})
            gate = CounterfactualDecisionGate(client, th, questions=EXTENDED_QUESTIONS)
        else:
            gate = CounterfactualDecisionGate(client, th)
    if a.config == "B":
        judge = BedrockJudge(os.environ.get("JUDGE_MODEL_ID", os.environ.get(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")),
            os.environ.get("AWS_REGION", "us-east-1"))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"meta": True, "config": a.variant or a.config, "split": a.split, "thresholds": th.model_dump(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "host_cpu": os.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1)}
    if gate is not None:
        meta["decider"] = gate.client.health()
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta) + "\n")
        for c in cases:
            rec = run_case(c, a.config, gate, judge, th)
            if a.config == "B" and rec.get("judge_status") == "ok":
                time.sleep(a.pace_s)  # pacing only; never counted in judge_latency_ms
            f.write(json.dumps(rec, default=str) + "\n")
            f.flush()
            ok = rec["committed"] == c.should_commit
            print(f"{c.case_id} {c.category:<22} label={'commit' if c.should_commit else 'block':<6} "
                  f"-> {rec['verdict']:<7} g={rec.get('grounded')} {'OK ' if ok else 'ERR'} "
                  f"{rec.get('judge_latency_ms')} ms", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

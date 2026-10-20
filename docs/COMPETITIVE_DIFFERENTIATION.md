# Competitive differentiation: TIME//SHIFT vs. SentryMesh

Reference reviewed: [Syedx2/sentrymesh-agent](https://github.com/Syedx2/sentrymesh-agent) at commit
`9d50fde` (2026-10-17). We read the source, not only the README. No code, prompts, assets or text
were copied. Observations describe that commit only and may not reflect later changes.

## 1. What SentryMesh does

SentryMesh is a cloud incident-response agent (AWS operations: cache flushes, IAM key quarantine,
database actions). Its architecture, from the source:

- `agent/decider_engine.py` calls a Decider endpoint and scores options for two patterns:
  a cloud guardrail (PROCEED / CONFIRM / GUIDE / DENY by blast radius and environment) and
  model routing (cache / deterministic tool / Bedrock / security block).
- `agent/bedrock_client.py` calls Bedrock through boto3 for a root-cause synthesis after the
  guardrail decision.
- `web/index.html` is a single-page dashboard.
- `benchmarks/latency_cost_benchmark.py` compares Decider against an LLM baseline.

Verified observations at `9d50fde`:

| Observation | Where |
|---|---|
| When the Decider endpoint is unreachable, `score_options` falls back to a keyword heuristic (`_compute_simulated_logits`) and adds `random.uniform(105.0, 118.0)` ms to the reported latency. The result is flagged `is_live_model=False`. | `agent/decider_engine.py` |
| The live path POSTs to `/score` with `{question, options, context}`. The documented `strands-decider serve` API is `POST /v1/systemone` with `{state, questions}`. | `agent/decider_engine.py`; upstream `docs/inference.md` |
| The LLM baseline in the benchmark uses fixed constants (`avg_llm_latency = 1850.0`, `p95_llm_latency = 2400.0`) and fixed per-call cost constants. | `benchmarks/latency_cost_benchmark.py` |
| The agent does not import Strands Agents or use an `InterventionHandler`. Orchestration is plain Python. | `agent/sentry_agent.py` |

These are factual descriptions of the code, not judgements of the project's merit.

## 2. Conceptual overlap

Both projects:
- target the **#guardrails** idea: a small model gates an agent action before it runs;
- pair Decider with Bedrock;
- present an operations dashboard.

## 3. What TIME//SHIFT does differently

| Capability | TIME//SHIFT | Status |
|---|---|---|
| **Counterfactual execution model.** Each candidate is executed in an isolated fork of a deterministic simulator over an identical horizon, including a do-nothing baseline, before anything is committed. | `src/timeshift/sim/fork.py` | **Working, tested** (branch-isolation and replay tests) |
| **The decision is about evidence grounding, not blast radius.** Decider is asked whether the action's premises are supported by *trusted* evidence, given the simulated futures. | `counterfactual_decision_gate/questions.py` | **Working with real inference** |
| **Simulation and semantics disagree on purpose.** In the signature scenario, the simulator ranks an ungrounded action first; Decider rejects it and the next-best grounded branch is committed. | `runs/solar_cascade.jsonl` | **Working, real Decider** (grounded=0.258 → DENY) |
| **Temporal consistency.** Commits require the live state revision; stale cited evidence is rejected deterministically. | `src/timeshift/mission.py` | **Working, tested** |
| **Strands-native wiring.** `InterventionHandler.before_tool_call` → `Proceed` / `Guide` / `Deny` / `Confirm`, with `on_error="deny"`. | `counterfactual_decision_gate/strands_handler.py` | Implemented; **agent path not yet run against Bedrock** (credentials blocked) |
| **No fallback.** Decider failure is DENY with an explicit status. The live path never substitutes a heuristic. | `counterfactual_decision_gate/gate.py` | **Working, tested** |
| **Official server API** (`/v1/systemone`, typed `noul` / `choice`, shared-prefix cache). | `counterfactual_decision_gate/client.py` | **Working** |
| **Replayable alternatives.** Every branch trajectory is recorded and can be scrubbed in the UI, including rejected futures. | `frontend/` | **Working** (recorded runs) |
| **Benchmark with labelled cases and real measurements for every configuration.** No constant baselines. | `bench/` | A and C: **measured**. B (LLM judge): **implemented, blocked on credentials** |

## 4. Differences that already work (evidence)

See [`EVIDENCE.md`](../EVIDENCE.md) for commands and outputs: real Decider verdicts on all three
scenarios, 49+ passing tests, and benchmark files in `bench/results/`.

## 5. Differences still planned

- Bedrock-driven proposals in the live agent loop (blocked: invalid AWS credentials on the dev machine).
- Config B (LLM judge) measurements (same blocker).
- AWS deployment on GPU (pending approval).

## 6. What we do NOT claim

- That TIME//SHIFT is safer in general, or that SentryMesh is invalid.
- Originality from theme, colour palette or 3D visuals. The claim rests on the counterfactual
  execution model, evidence-grounding decision and temporal checks above.

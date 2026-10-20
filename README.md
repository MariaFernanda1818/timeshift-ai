# TIME//SHIFT

**Explore possible futures. Verify decisions. Change the outcome.**

TIME//SHIFT is a mission-control agent for a simulated lunar base. During an emergency it
forks the simulation into one future per candidate action, measures every future, and asks
**Strands Decider 2B** whether each action rests on trusted evidence or on an invented,
unverified or contradicted premise. Only then does it commit exactly one action.

> A conventional agent picks an action. TIME//SHIFT explores the consequences, checks the
> evidence, and only then commits.

**Bedrock proposes. Simulation explores. Decider evaluates. Deterministic policies enforce.**

![Dashboard: the simulator's top-ranked future (B3) rejected by Decider](docs/screenshots/agent-solar_cascade-r1-B3-1440.png)

## The decision Decider 2B makes (pattern: `#guardrails`)

Signature scenario `solar_cascade`: a micrometeoroid strike cuts solar output to 45% and the
battery heads for a brownout. An unvalidated anomaly classifier recommends sealing the habitat
(HAB) for a "possible micro-fracture", while HAB's own sensors read nominal. Bedrock (via Strands)
proposes its own candidates. TIME//SHIFT forks four futures (including do-nothing), screens
every one with Decider, and commits the best grounded branch.

Real end-to-end runs: 5 rehearsals, Bedrock Claude Haiku 4.5 + Decider 2B on CPU
(`runs/agent-solar_cascade-r*.jsonl`):

| Branch | Proposed by | Simulated score | Decider `evidence_grounded` | Outcome |
|---|---|---|---|---|
| isolate HAB | anomaly classifier | **0.772, #1 in 5/5** | **0.333–0.347** | **DENY 5/5** |
| shed LAB load (reroute) | Bedrock | 0.769 | 0.751–0.814 | committed 5/5 |
| activate backup power | Bedrock | 0.760 | 0.808–0.873 | approved, not chosen |

The simulator alone would have sealed the habitat: shedding its load really does help. Only an
evidence check can tell that the reason is unfounded.

## What we measured

40 labelled synthetic proposals (10 calibration / 30 held out), identical inputs for every
configuration (details and caveats: [EVIDENCE.md](EVIDENCE.md)):

| Held-out (n=30) | Unsupported authorised | Supported blocked | Accuracy | Median judge latency |
|---|---|---|---|---|
| A: deterministic policy only | 13 | 0 | 0.567 | — |
| B: + Bedrock LLM judge | 0 | 1 | 0.967 | 1.2 s |
| C: + Decider 2B (threshold from calibration) | 0 | 2 (+14 human reviews) | 0.933 | 32 s (laptop CPU) |
| D: Decider first, uncertain band → LLM judge (offline, recorded data) | 0 | 0 | 1.000 | 33.5 s (CPU) |

**The general LLM judge was more accurate than Decider alone on this benchmark.** Decider was
reliable on unverified premises but scored real-evidence/wrong-target actions too high. We report
this as measured. The cascade (D) is now an optional mode (`TIMESHIFT_ESCALATION`, below).

## How it works

```
incident ─► Bedrock agent (Strands) proposes candidates; automated subsystems may add one
              │ fork_reality tool
              ▼
          deterministic simulator: B0 no-op + B1..B3, identical seed & horizon, isolated copies
              ▼
          screen EVERY branch: deterministic policy (allowlist, schema, preconditions,
          revision freshness, idempotency) + Strands Decider 2B /v1/systemone noul question
              ▼
          agent calls commit_action ─► InterventionHandler.before_tool_call
              ▼  PROCEED → Proceed | DENY → Guide (pick another) | REVIEW → Confirm / operator
          orchestrator re-checks and commits exactly one action (revision +1) or abstains
              ▼
          structured explanation, every number and branch claim checked against the simulation
```

| Path | What it is |
|---|---|
| `src/timeshift/sim/` | pure, deterministic, immutable simulation ([docs/SIMULATION.md](docs/SIMULATION.md)) |
| `src/timeshift/mission.py` | orchestrator: the only mutation path, screening, temporal checks, human review |
| `src/timeshift/agent.py` | Strands agent on Amazon Bedrock with the gate as an intervention |
| `src/timeshift/explain.py` | evidence packet + deterministic claim check for explanations |
| `reusable-patterns/counterfactual-decision-gate/` | **the reusable, application-agnostic pattern** |
| `frontend/` | React + Three.js mission control, event-driven (live SSE or recorded replays) |
| `bench/` | labelled cases, A/B/C harness, calibration and cascade analysis |

## What is real and what is not

| Kind | Where |
|---|---|
| **Real model inference** | Decider 2B (`strands-decider-2B-qwen3.5-v1-2610`, local server) and Bedrock Claude Haiku 4.5. Every decision record stores checkpoint, probabilities and latency. Bedrock request IDs are logged. |
| **Simulated mission outcomes** | Every telemetry value and branch outcome comes from the illustrative simulator, never from an LLM. |
| **Fixture scenarios** | `runs/fixture-*.jsonl` and the benchmark use hand-written candidate sets (`src/timeshift/fixtures.py`). The UI labels them. Verdicts in them are still real Decider inference. |
| **Scripted subsystem** | The "anomaly classifier" recommendation is scenario data, labelled as unvalidated. |
| **Benchmark measurements** | `bench/results/*.jsonl`, one line per measured case. |

## Quick start (local, CPU)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe "strands-decider @ git+https://github.com/strands-labs/strands-decider@930e6d5de16309be32579f5631a7369a3322140c"
uv pip install --python .venv/Scripts/python.exe -e ".[dev]" -e "reusable-patterns/counterfactual-decision-gate[strands]" "botocore[crt]"
.venv/Scripts/strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099 --device cpu
python scripts/validate_env.py                               # environment, Bedrock and Decider checks
pytest -q                                                    # 69 unit tests (no model needed)
python scripts/run_cycle.py --scenario solar_cascade --out runs/fixture-solar_cascade.jsonl
AWS_PROFILE=... python scripts/run_agent.py --scenario solar_cascade --out runs/agent-solar_cascade.jsonl
(cd frontend && npm ci && npm run build)
uvicorn timeshift.server:app --port 8080                     # open http://127.0.0.1:8080
```

Configuration: see [.env.example](.env.example). `DECIDER_PROCEED_AT` sets the PROCEED threshold
(default 0.70; 0.90 was chosen on the calibration split). `TIMESHIFT_ESCALATION=bedrock` sends only
Decider's review band to the Bedrock judge; a Decider failure still denies.

On CPU each gate call takes ~30–45 s for ~1,300-token states (i5-1235U). See
[docs/AWS_DEPLOYMENT.md](docs/AWS_DEPLOYMENT.md) for the GPU deployment plan (not yet provisioned).

## Honesty notes

- The simulation is illustrative, not aerospace-grade.
- Decider's probabilities are model outputs, not calibrated accuracy guarantees.
- Deterministic checks (stale evidence, unknown IDs, unsafe transitions) are credited to the
  policy engine, not to Decider.
- Status: [PROJECT_STATUS.md](PROJECT_STATUS.md) · Measurements: [EVIDENCE.md](EVIDENCE.md) ·
  Decisions: [DECISIONS.md](DECISIONS.md) · Competition: [docs/COMPETITIVE_DIFFERENTIATION.md](docs/COMPETITIVE_DIFFERENTIATION.md)

## License

MIT (this repository). Strands Decider is Apache-2.0.

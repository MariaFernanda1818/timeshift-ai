# TIME//SHIFT

**Explore possible futures. Verify decisions. Change the outcome.**

TIME//SHIFT is a mission-control agent for a simulated lunar base. During an emergency it
forks the simulation into one future per candidate action, measures every future, and commits
an action only if **Strands Decider 2B** judges that the action rests on trusted evidence and
not on an invented, unverified or contradicted premise.

> A conventional agent picks an action. TIME//SHIFT explores the consequences, checks the
> evidence, and only then commits.

**Bedrock proposes. Simulation explores. Decider evaluates. Deterministic policies enforce.**

![Dashboard: the simulator's top-ranked future B3 rejected by Decider](docs/screenshots/solar_cascade-B3-1440.png)

## The decision Decider 2B makes

In the signature scenario (`solar_cascade`), a micrometeoroid strike cripples the solar field.
Three candidates are forked over 20 ticks (real run, CPU, recorded in `runs/solar_cascade.jsonl`):

| Branch | Action | Simulated score | Premise | Decider `evidence_grounded` | Gate |
|---|---|---|---|---|---|
| B3 | isolate HAB | **0.772 (#1)** | unverified classifier flag R-HAB-01, contradicted by HAB sensors | **0.258** | **DENY** |
| B1 | activate backup power | 0.760 (#2) | telemetry E000-PWR, E000-BKP | 0.885 | **PROCEED → committed** |
| B2 | EVA solar repair | 0.755 (#3) | telemetry | not needed | — |

The simulator alone would have chosen B3: shedding the habitat really does save power. Only an
evidence-grounding check can tell that the reason for doing it is unfounded. That is
the job given to Decider: the **Counterfactual Decision Gate** (pattern tag **#guardrails**).

## How it works

```
incident ─► Bedrock agent (Strands) proposes ≤3 candidates
              │ fork_reality tool
              ▼
          deterministic simulator: B0 no-op + B1..B3, identical seed & horizon, isolated copies
              │ commit_action tool  ──► InterventionHandler.before_tool_call
              ▼
          deterministic policy (allowlist, schema, preconditions, revision freshness, idempotency)
              ▼
          Strands Decider 2B  /v1/systemone  noul "evidence_grounded" + choice "verdict"
              ▼
          thresholds in code ─► Proceed | Guide (try next branch) | Confirm/Deny
              ▼
          orchestrator re-checks and commits exactly one action (revision +1) or abstains
```

- `src/timeshift/sim/`: pure, deterministic, immutable simulation ([docs/SIMULATION.md](docs/SIMULATION.md))
- `src/timeshift/mission.py`: orchestrator, the only mutation path; temporal checks; event log
- `src/timeshift/agent.py`: Strands agent on Amazon Bedrock with the gate as an intervention
- `reusable-patterns/counterfactual-decision-gate/`: the **application-agnostic reusable pattern**
- `frontend/`: React + Three.js mission control, event-driven (live SSE or recorded replays)
- `bench/`: labelled cases and the A/B/C benchmark

## Quick start (local, CPU)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe "strands-decider @ git+https://github.com/strands-labs/strands-decider@930e6d5de16309be32579f5631a7369a3322140c"
uv pip install --python .venv/Scripts/python.exe -e ".[dev]" -e "reusable-patterns/counterfactual-decision-gate[strands]"
.venv/Scripts/strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099 --device cpu
python scripts/validate_env.py                         # environment + real Decider check
pytest -q                                              # unit tests (no model needed)
python scripts/run_cycle.py --scenario solar_cascade --out runs/solar_cascade.jsonl
(cd frontend && npm ci && npm run build)
uvicorn timeshift.server:app --port 8080               # open http://127.0.0.1:8080
```

On CPU each gate call takes tens of seconds (measured: 26–53 s for ~1,300-token states on an
i5-1235U). See [docs/AWS_DEPLOYMENT.md](docs/AWS_DEPLOYMENT.md) for the GPU deployment plan.

## Honesty notes

- The simulation is illustrative, not aerospace-grade.
- Decider's probabilities are model outputs, not calibrated accuracy guarantees.
- Fixture runs use hand-written candidates (labelled `proposer: fixture`). Live runs use Bedrock.
- Deterministic checks (stale evidence, unknown modules, unsafe transitions) are credited to
  the policy engine, not to Decider.
- Status of every component: [PROJECT_STATUS.md](PROJECT_STATUS.md). Measurements:
  [EVIDENCE.md](EVIDENCE.md). Decisions: [DECISIONS.md](DECISIONS.md).

## License

MIT (this repository). Strands Decider is Apache-2.0.

# Project status

_Last updated: 2026-10-20 (day 3 of 5). Deadline: 2026-10-23 11:59 PM PDT._

**Current phase:** end-to-end works locally with real Bedrock and real Decider. Benchmark A/B/C
re-run is in progress. AWS deployment is waiting on a restricted IAM identity and budget approval.

## Status matrix

| Component | Implemented | Tested | Real or mock | Classification | Remaining |
|---|---|---|---|---|---|
| Deterministic simulator (5 actions, 3 scenarios) | yes | 24 tests | real | **VERIFIED** | optional 4th scenario |
| FORK REALITY (isolated branches, no-op baseline, scoring) | yes | isolation/replay tests | real | **VERIFIED** | — |
| Screening of every forked branch by the gate | yes | 4 tests + 5 real runs | real | **VERIFIED** | — |
| Orchestrator (single mutation path, policy, temporal checks, idempotency) | yes | tests | real | **VERIFIED** | — |
| Human review path (REVIEW → operator approve/reject) | yes | 5 tests | real | **VERIFIED** (unit); UI built, not yet exercised in a live browser run | live UI check |
| External proposer (unvalidated classifier recommendation) | yes | test + 5 real runs | real | **VERIFIED** | — |
| Decider 2B (`strands-decider-2B-qwen3.5-v1-2610`), CPU | yes | live tests, benchmark, agent runs | **real** | **VERIFIED** (local CPU) | GPU |
| Reusable pattern (gate, client, handler, cached decisions) | yes | 16 unit + 1 live | real | **VERIFIED** | — |
| Strands `InterventionHandler` on the agent path | yes | 5 real agent runs | real | **VERIFIED** | — |
| Amazon Bedrock (Claude Haiku 4.5 via Strands) | yes | real invocations, request IDs logged | real | **VERIFIED**, but identity is **root** (temporary) | restricted IAM identity |
| Structured explanations + deterministic claim check | yes | 4 tests + 5 real runs (0 unsupported claims) | real | **VERIFIED** | — |
| IT-ops example agent (pattern reuse) | yes | 1 real run | real | **VERIFIED** | — |
| FastAPI + SSE + replays + review endpoint | yes | curl smoke + Playwright | real | **VERIFIED** (local) | — |
| Dashboard | yes | screenshots 1920/1440/390, no console errors | real events | **VERIFIED** (replay) | live-mode recording |
| Benchmark A / C / C2 (v1, before report text change) | yes | 40 cases | real | **VERIFIED**, archived in `bench/results/v1/` | — |
| Benchmark A / B / C (v2, current scenario text) | yes | running | real | **IN PROGRESS** | summarize |
| AWS deployment (g6.xlarge, private, SSM) | scripts + docs | — | — | **INCOMPLETE**: needs restricted identity, GPU quota, approval | provision, validate |
| Builder Center article | draft `docs/ARTICLE.md` | — | — | **INCOMPLETE** | numbers from v2 benchmark + deployment |
| Demo script / submission checklist | `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION_CHECKLIST.md` | — | — | drafted | record video |
| Public repository | local only, **no commits yet** | — | — | **INCOMPLETE** | owner approval |

## Tests executed

`pytest -q` → **64 passed**, 1 live test deselected. Live tests pass against the real Decider server.

## Known issues

- Decider on CPU: 31–46 s per gate call; a full agent run takes ~2 min (3 gate calls). Needs a GPU for a live demo.
- New AWS account is rate-limited on Bedrock (`ThrottlingException` during the LLM-judge benchmark).
  Mitigated with pacing and adaptive retries.
- The `timeshift` profile resolves to the **root** user and has no region configured.
- Early fixture recordings (`runs/solar_cascade.jsonl` etc.) predate branch screening and the
  external proposer. Re-record before the demo.

## Next actions

1. Finish the A/B/C v2 benchmark and analyse where Decider and the LLM judge differ.
2. **Owner:** create a restricted IAM identity; approve the EC2 budget; request GPU quota.
3. Deploy, run `validate_env.py` on EC2, and measure GPU latency.
4. Re-record fixture runs and screenshots; record the video; finalise the article.

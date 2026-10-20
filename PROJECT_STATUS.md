# Project status

_Last updated: 2026-10-20 (day 3 of 5). Deadline: 2026-10-23 11:59 PM PDT._

**Current phase:** end-to-end verified locally with real Bedrock and real Decider. A/B/C/D benchmark
complete. Local commits made, nothing published. AWS deployment waits on the restricted IAM identity,
followed by a verified GPU/quota/pricing plan and owner approval.

## Status matrix

| Component | Implemented | Tested | Real or mock | Classification | Remaining |
|---|---|---|---|---|---|
| Deterministic simulator (5 actions, 3 scenarios) | yes | 24 tests | real | **VERIFIED** | optional 4th scenario |
| FORK REALITY (isolated branches, no-op baseline, scoring) | yes | isolation/replay tests | real | **VERIFIED** | — |
| Screening of every forked branch by the gate | yes | 4 tests + 5 real runs | real | **VERIFIED** | — |
| Orchestrator (single mutation path, policy, temporal checks, idempotency) | yes | tests | real | **VERIFIED** | — |
| Human review path (REVIEW → operator approve/reject) | yes | 5 tests + live server run (SSE → awaiting_review → approve → commit, real Decider) | real | **VERIFIED** (API); UI buttons not clicked in a browser yet | browser click-through |
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
| Benchmark A / B / C (v2) + calibration + cascade D (offline) | yes | 40 cases each | real | **VERIFIED** | more cases would strengthen D |
| Optional REVIEW-band escalation to Bedrock judge (`TIMESHIFT_ESCALATION`) | yes | 5 unit tests | real when enabled | **IMPLEMENTED BUT UNVERIFIED (live)**: AWS login session expired before the live check | run with dev identity |
| Fixture recordings with screening (3 scenarios) | yes | real Decider | fixture proposals, real inference | **VERIFIED** | — |
| AWS deployment (g6.xlarge, private, SSM) | scripts + docs | — | — | **INCOMPLETE**: needs restricted identity, GPU quota, approval | provision, validate |
| Builder Center article | `docs/ARTICLE.md` with v2 benchmark + rehearsal numbers | — | — | **INCOMPLETE** | GPU latency, deployment evidence, links |
| Demo script / submission checklist | `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION_CHECKLIST.md` | — | — | drafted | record video |
| Local git history | 7+ commits, LF-safe shell scripts, CI workflow (pytest, ruff, frontend build) | — | — | **VERIFIED locally** (CI not run: not pushed) | publish on approval |

## Tests executed

`pytest -q` → **69 passed**, 1 live test deselected. `ruff check` clean. Live tests pass against the real Decider server.

## Known issues

- Decider on CPU: 31–46 s per gate call; a full agent run takes ~2 min (3 gate calls). Needs a GPU for a live demo.
- New AWS account is rate-limited on Bedrock (`ThrottlingException` during the LLM-judge benchmark).
  Mitigated with pacing and adaptive retries.
- The `timeshift` profile resolves to the **root** user (region now set to us-east-1). Its login session
  expired on 2026-10-20. We are deliberately not re-authenticating as root.
- Legacy recordings moved to `runs/v1/` (pre-screening). Current: `runs/fixture-*.jsonl`, `runs/agent-solar_cascade-r1..5.jsonl`.
- Decider approves relevant-looking but unnecessary actions that cite real telemetry (benchmark E18;
  backup power in `fixture-reactor_overheat` 0.877). These were not committed because a better branch won.

## Next actions

1. **Owner:** finish the restricted development identity.
2. With it: verify GPU instance availability, the G/VT vCPU quota, current pricing and credit
   eligibility; refresh the deployment plan; ask for approval.
3. Live check of the REVIEW-band escalation.
4. After approval: deploy, run `validate_env.py` on EC2, measure GPU latency, record the video
   from the deployed instance, finalise and publish the article and repository (owner approval).

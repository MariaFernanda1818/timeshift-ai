# Project status

_Last updated: 2026-10-21 (night). Deadline: 2026-10-23 11:59 PM PDT; target: submission-ready by 2026-10-22 night.
**Feature freeze in effect.**_

## Submission readiness

### Mandatory blockers (cannot submit without these)

| # | Blocker | Why blocked | Unblocked by |
|---|---|---|---|
| 1 | Agent running **on AWS** (EC2 + Bedrock + Decider) | no non-root identity; deployment not approved | owner: dev identity → readiness check → approval |
| 2 | Public GitHub repository | publication needs approval. Audit done; history rewritten to the GitHub noreply email (17 commits, trees/dates/messages verified identical, backup bundle in `C:\timeshift-ai-backup`) | owner: approve `git push origin main` (main only, no tags) |
| 3 | Public demo video < 3 min | should be recorded from the AWS deployment (fallback: local, labelled) | after #1, or owner accepts local recording |
| 4 | Builder Center article published with `#strands-decider-2b` `#guardrails` | needs repo + video links and GPU/deployment numbers | after #1–#3; owner publishes |
| 5 | ~~Bedrock re-verified with the dev identity~~ | ✅ done 2026-10-22 (request ae3a1d3c-…) | — |

### Done and verified (local)
Simulator + FORK REALITY, branch screening, deterministic policy + temporal checks, Decider 2B gate
(real inference), Strands `InterventionHandler` on the Bedrock agent path (5/5 rehearsals), human
review path (live server), structured explanations with claim checks, reusable pattern + IT-ops
example, dashboard (screenshots at 3 widths), benchmarks A/B/C/D v2 and eval2 A/C, CloudFormation
template (cfn-lint clean), read-only readiness script, repository audit.

### Optional experimental improvements (NOT required for submission)
- eval2 live B and D (Bedrock; < $0.10; ~25 min CPU). Valuable for the article's confirmatory claim.
- Live check of the REVIEW-band escalation in the app.
- More benchmark cases; GPU re-run of the benchmark.
- UI click-through of the Approve/Reject buttons in a browser.

### Estimated deployment cost: planned cap US$15 (details in docs/AWS_DEPLOYMENT.md; third-party prices until `scripts/aws_readiness.py` runs)

| Path | Instance | ~$/h | 12 h window | Notes |
|---|---|---|---|---|
| GPU (preferred) | g6.xlarge | ~0.80 | ~$10 | needs G/VT vCPU quota ≥ 4 |
| CPU fallback | c7i.2xlarge (16 GiB) or c7i.4xlarge (32 GiB) | ~0.36 / ~0.71 | ~$4 / ~$9 | Decider tens of seconds per call |
| + EBS 100 GiB, Bedrock tokens, transfer | — | — | ~$3 | |
| **Total** | | | **≈ $7–13** | stack deleted after recording |

### Exact owner actions
1. ✅ Identity `timeshift-dev` verified; ✅ readiness policy attached; ✅ readiness run (Bedrock OK, 5 policies valid, template valid, G/VT quota 0 → CPU path m7i-flex.large). Next: owner creates the two pre-created roles (`deploy/iam/README.md` Step 2), approves push + deployment.
2. Check Billing → Credits for EC2 GPU/Bedrock eligibility, and request the G/VT quota (≥ 4 vCPU) if it is 0.
3. Approve: (a) the deployment path and cost, (b) publishing the GitHub repo (and which author email to keep public), (c) uploading the video, (d) publishing the article.
4. Close memory-heavy apps before recording (IntelliJ, browser tabs): the laptop had 1–2 GB free RAM during runs.

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
| AWS deployment (g6.xlarge, private, SSM; c7i CPU fallback) | CloudFormation (cfn-lint clean), GPU/CPU user-data, read-only readiness script, suggested dev IAM policy | lint only | — | **PREPARED, NOT PROVISIONED**: needs dev identity → readiness → approval | run readiness, deploy, capture evidence |
| Confirmatory cascade evaluation (eval2, pre-registered, frozen thresholds) | cases + live config D + abstention metrics | A and C done (C: 4 wrong commits, 3 wrong blocks, 13 reviews); B and D need Bedrock | real | **IN PROGRESS** | B, D live with dev identity |
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

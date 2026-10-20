# Submission checklist: AWS Strands Decider Agent Experience Hackathon

Deadline: **2026-10-23 11:59 PM PDT** (verified on the hackathon page 2026-10-18).

| # | Requirement | Evidence | Status |
|---|---|---|---|
| 1 | Original agent, not previously published | new repo, first commit 2026-10 | ☐ confirm at submission |
| 2 | Uses Strands Decider 2B for a meaningful decision | evidence-grounding gate on every forked branch; 5/5 real rehearsals `runs/agent-solar_cascade-r*.jsonl` | ✅ local (CPU) |
| 3 | Paired with Amazon Bedrock | `src/timeshift/agent.py`; real runs and LLM-judge benchmark in EVIDENCE.md | ✅ verified with a temporary root session, to be re-verified with the dev identity |
| 4 | Working AI agent on AWS | `docs/AWS_DEPLOYMENT.md` | ☐ **needs approval + restricted IAM identity** |
| 5 | Public repository with full source | local repo | ☐ needs approval to publish |
| 6 | ≥1 reusable Decider 2B decision pattern (typed question + options, wiring, usage note) | `reusable-patterns/counterfactual-decision-gate/` | ✅ |
| 7 | Public demo video < 3 min | `docs/DEMO_SCRIPT.md` | ☐ record |
| 8 | Builder Center article (agent, what it does, the Decider decision, learnings) | `docs/ARTICLE.md`: real benchmark and rehearsal numbers; GPU/deployment/links pending | ☐ finalize + publish (approval) |
| 9 | Tags: `#strands-decider-2b` + exactly one pattern tag: `#guardrails` | article header | ☐ |
| 10 | Exactly one declared decision pattern | Guardrails: Counterfactual Decision Gate | ✅ |
| 11 | Eligibility (18+, Builder Center profile, country) | owner | ☐ owner |
| 12 | License present | MIT `LICENSE`; Decider is Apache-2.0 (attributed) | ✅ |
| 13 | No secrets in repo | `git grep -I -E "AKIA|aws_secret|login_session"` before push | ☐ run before publishing |
| 14 | Claims match EVIDENCE.md | review pass | ☐ |
| 15 | Video shows real inference, labels fixture vs Bedrock runs, and states CPU/GPU honestly | `docs/DEMO_SCRIPT.md` | ☐ |

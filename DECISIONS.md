# Architectural decisions

Format: decision · why · alternatives considered · date.

### D1 — Decider checkpoint: `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610`
The 2B reference model, released 2026-10-09, matches the hackathon's "Decider 2B". Installed from
`strands-decider` git commit `930e6d5` (PyPI 0.1.0 lacks the current device extras). Gemma
variants are larger (E2B needs ~19 GB fp32 on CPU). 2026-10-18.

### D2 — Gate wiring through Strands `InterventionHandler.before_tool_call`
This is the official seam (see `examples/strands/tool_call_intervention.py` upstream). Strands 1.61.1
provides `Proceed`, `Deny`, `Guide` and `Confirm`. Mapping: PROCEED→`Proceed`, DENY→`Guide`
(the agent gets the reason and picks the next branch) or `Deny`, REVIEW→`Confirm` (human) or
`Deny` (unattended). `on_error="deny"` gives fail-closed behaviour. 2026-10-18.

### D3 — Decider judges evidence grounding, not safety or numbers
The simulator computes consequences. Deterministic policy enforces invariants (allowlist,
schema, preconditions, revision freshness, idempotency, repeat window). Decider answers one
narrow semantic question: are the action's premises supported by TRUSTED evidence? A generic
"is this safe?" classifier was rejected: it overlaps with the deterministic layer and is not
falsifiable. 2026-10-18.

### D4 — The signature scenario is designed so the simulator's #1 branch is ungrounded
In `solar_cascade`, isolating HAB has the best simulated score (0.772), because shedding 4.5 kW
really does help. Its premise, however, comes only from an unverified classifier flag
(R-HAB-01) that HAB's own sensors contradict. This shows why simulation alone is not enough:
numbers cannot reveal a false premise. The scenario parameters (HAB load 4.5 kW, solar 45%,
backup 4 kWh) were tuned so this ranking holds. A test pins it
(`test_signature_scenario_unsupported_branch_ranks_first`). The Decider verdict is NOT tuned
or overridden. 2026-10-18.

### D5 — Fail closed, never substitute
Any Decider error is DENY with an explicit `decider_status`. There is no heuristic or LLM fallback
in the gate. The UI shows the Decider health badge. 2026-10-18.

### D6 — Temporal consistency is deterministic
Proposals carry `based_on_revision` and `based_on_tick`. Commit requires the live revision.
Cited trusted evidence older than 3 ticks is rejected. These are code checks recorded as
`STALE:` violations. They are not credited to Decider. 2026-10-18.

### D7 — Scoring function
`score = 0.35·crew + 0.15·oxygen + 0.20·power + 0.15·reactor + 0.10·continuity + 0.05·resources`.
Each component is normalised to 0..1 (see `sim/fork.py`). Continuity was added after the first
sweep showed brownouts were not penalised. Weights are illustrative and configurable
(`ScoreWeights`). 2026-10-18.

### D8 — One FastAPI process + one Decider process; SSE, one event schema
Live streams and recordings share `timeshift.mission.Event`, so a replay is a verbatim
re-emission of recorded events. No microservices. 2026-10-18.

### D9 — Fixture proposer kept alongside the Bedrock proposer
A hand-written candidate set per scenario makes benchmark configurations comparable and lets
the pipeline run while Bedrock is unavailable. Every event records `proposer`, and the UI labels
fixture runs. 2026-10-18.

### D10 — Policy keys on the `noul` grounding question
In the first real runs, the `choice` verdict question returned "proceed" for the ungrounded HAB
action (p=0.53–0.64), while `evidence_grounded` was 0.26–0.30. The policy uses grounding as the
primary signal and lets `verdict` only escalate a confident `deny`. To be re-checked against the
benchmark. 2026-10-18.

### D11 — AWS target: single g6.xlarge, private, SSM access
CPU latency of 26–53 s per gate call is too slow for a live loop. L4 GPU at ~$0.80/h. No public
ingress. Pending owner approval and a valid AWS credential. 2026-10-18.

### D13 — Gate every forked branch, not only the agent's choice (2026-10-19)
In real runs, Bedrock sometimes picked a lower-ranked branch by itself, so an ungrounded top branch
was never evaluated. TIME//SHIFT now screens every branch right after the fork
(`Mission.screen`). The agent sees each GATE verdict alongside the simulated outcome, and
`commit_action` reuses the screened decision (`cached_decision`). Reuse is bound to the fork,
action key and state revision, and only happens if the deterministic policy still passes at that
moment. Cost: one Decider call per branch.

### D14 — External proposers (2026-10-19)
Automated subsystems (here, the unvalidated anomaly classifier) can submit recommendations
into the fork. They take one of the 3 candidate slots, are labelled with their source, and are gated
like any proposal. The HAB candidate in the signature scenario comes from this path, not from
Bedrock, because Bedrock did not propose it on its own.

### D15 — Human review path (2026-10-19)
REVIEW verdicts can be committed only through `Mission.resolve_review(..., approve=True)` with an
operator id. The approval is recorded on the commit event, and the deterministic policy is re-run.
DENY can never be approved. Server: `POST /api/missions/{id}/review`; the UI shows Approve/Reject.
Threshold via `DECIDER_PROCEED_AT` (default 0.70, calibrated value 0.89).

### D12 — Question set after the benchmark
`evidence_grounded` (noul) is the decisive question. The `choice` verdict said `proceed` in 29/29
cases, so it is kept for audit only and can only escalate a confident `deny`. The
`addresses_situation` variant (C2) was rejected on the calibration split. Calibrated threshold:
`proceed_at = 0.89` (chosen on calib; eval: 2 wrong commits / 1 wrong block / 11 REVIEW).
**Open decision for the owner:** use the calibrated threshold for the demo. The signature run's B1
(0.885) then becomes REVIEW, so a human Confirm is needed before the commit. 2026-10-18.

# Counterfactual Decision Gate

A reusable **Strands Decider 2B** decision pattern for **#guardrails**.

> Before an agent commits a consequential action, simulate the alternatives, then ask a
> small typed decision model one narrow question: *is this action grounded in trusted
> evidence, or does it rest on an invented, unverified or contradicted premise?*

The pattern is application-agnostic. It works for infrastructure incident response,
financial workflows, IT operations, workflow automation, simulated robotics, resource
management, or any agent with a "commit" step and some way to preview consequences.

## Separation of responsibilities

| Layer | Owns | Never does |
|---|---|---|
| Your LLM agent (e.g. Bedrock via Strands) | proposes actions, explains | mutates state directly |
| Your simulator / dry-run | numerical consequences of each candidate | judges evidence |
| **Strands Decider 2B** | typed semantic judgement: is the action evidence-grounded? | enforce invariants, predict numbers |
| `hard_checks` (your code) | allowlists, schemas, bounds, preconditions, freshness | defer to the model |
| `Thresholds` (your code) | turn probabilities into PROCEED / REVIEW / DENY | — |

**A hard-check violation is always DENY, even if Decider is 0.99 confident.**
**If Decider is unreachable, times out or answers malformed JSON, the gate fails closed (DENY).**
It never substitutes a heuristic or another model.

## The typed questions

Sent to `POST /v1/systemone` of `strands-decider serve` (see `questions.py`):

| Name | Type | Instructions | Options |
|---|---|---|---|
| `evidence_grounded` | `noul` | Is every premise and argument of the proposed action supported by TRUSTED evidence, without relying on unverified reports or invented facts? | `true`: every argument and premise is confirmed by trusted evidence · `false`: relies on an unverified report, an invented value, or a premise trusted evidence contradicts |
| `verdict` | `choice` | Given the trusted evidence and the simulated outcomes, what should happen to the proposed action? | `proceed` · `review` · `deny` (each with a description) |

Both questions share one encoded state (Decider's shared-prefix cache), so asking the second
costs only its own tokens.

**Measured caveats (TIME//SHIFT benchmark, 40 labelled cases):**
- The `noul` grounding question carried the signal: unverified premises scored 0.25–0.30 and
  supported actions 0.88–0.94.
- The `choice` verdict question answered `proceed` in 29/29 cases. The default policy only uses
  it to escalate a confident `deny`.
- Grounding does **not** detect actions that cite real evidence but target the wrong component
  (0.82–0.89). Pair the gate with your simulator's outcome comparison and deterministic checks.
- A threshold chosen on 10 calibration cases (`proceed_at=0.89`) cut wrongly authorised actions
  on 30 held-out cases from 13 (deterministic only) to 2, with 1 wrong block and 11 sent to review.

See the project's `EVIDENCE.md` for every number.

## Default policy

```
grounded <  deny_below (0.40)                        -> DENY
verdict == deny with confidence >= 0.60              -> DENY
grounded >= proceed_at (0.70) and verdict != deny    -> PROCEED
otherwise                                            -> REVIEW
```

Thresholds are code (`Thresholds`), chosen on a calibration split, not model guarantees.
Decider's confidence is not empirical accuracy.

## Strands wiring

`CounterfactualGateHandler` is a Strands `InterventionHandler` that runs in
`before_tool_call`, on the agent's real execution path:

| Verdict | Strands action |
|---|---|
| PROCEED | `Proceed()` |
| DENY | `Guide(feedback)` (agent picks another action) or `Deny(reason)` with `deny_mode="deny"` |
| REVIEW | `Confirm(prompt)` (human approval) or `Deny` with `review_mode="deny"` for unattended agents |

`on_error = "deny"`, so an exception inside the handler blocks the tool call.

## Usage

```python
from counterfactual_decision_gate import (
    CounterfactualDecisionGate, DeciderClient, GateRequest, EvidenceItem, Thresholds)
from counterfactual_decision_gate.strands_handler import CounterfactualGateHandler

gate = CounterfactualDecisionGate(
    DeciderClient("http://127.0.0.1:8099", timeout_s=120,
                  expected_checkpoint="StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"),
    thresholds=Thresholds(proceed_at=0.70, deny_below=0.40),
    hard_checks=my_deterministic_checks,          # -> list[str] of violations
)

def build_request(tool_name, args, event) -> GateRequest:
    return GateRequest(
        action_name=tool_name, action_args=args,
        situation="...", evidence=[EvidenceItem(evidence_id="M1", text="...", trusted=True)],
        rationale="...", cited_evidence=["M1"],
        proposed_branch=my_simulator(tool_name, args),          # CounterfactualBranch
        alternatives=[my_simulator(a, x) for a, x in other_candidates])

agent = Agent(model=..., tools=[...],
              interventions=[CounterfactualGateHandler(gate, build_request,
                                                       gated_tools={"commit_change"})])
```

A full runnable example for an IT-operations agent is in
[`examples/it_ops_agent.py`](examples/it_ops_agent.py).

## Adapting it

1. **Evidence:** mark what is trusted (sensors, APIs, signed records) vs. untrusted (chat,
   heuristics, LLM text). Give every item an ID the agent can cite.
2. **Counterfactual:** any deterministic preview works: a simulator, `terraform plan`, a
   ledger dry-run, a robot motion planner. Put only its measured outputs in `summary`.
3. **Hard checks:** everything mandatory belongs here, not in Decider.
4. **Calibrate:** label a small set of your own proposals and choose `proceed_at` /
   `deny_below` on it. Hold out a separate set to report accuracy.

## Failure handling

| Condition | Result |
|---|---|
| Server unreachable / HTTP 5xx | `DENY`, `decider_status="unavailable"` |
| Timeout | `DENY`, `decider_status="timeout"` |
| Malformed or out-of-range answer | `DENY`, `decider_status="malformed"` |
| Checkpoint ≠ `expected_checkpoint` | `DENY`, `decider_status="version_mismatch"` |
| Hard-check violation | `DENY`, Decider skipped (or consulted for audit with `ask_on_hard_violation=True`) |
| Grounding in the review band | `REVIEW` → `Confirm` or `Deny` |

## Tests

```bash
pytest reusable-patterns/counterfactual-decision-gate/tests                 # unit (test doubles, labelled)
pytest -m live reusable-patterns/counterfactual-decision-gate/tests -s      # real Decider server
```

## Security note

`strands-decider serve` binds to `127.0.0.1` without authentication. Keep it private
(localhost, a private subnet or a security group that admits only the agent host). The
client can send a bearer token (`STRANDS_DECIDER_TOKEN`) if you put an authenticating
proxy in front of it.

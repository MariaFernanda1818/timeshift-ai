# Demo video script: "The future that should never have happened"

Target length: **2:45** (hard limit < 3:00). English voice-over and burned-in captions.
Every on-screen decision comes from a recorded real run (`runs/agent-solar_cascade-r1..r5.jsonl`:
Bedrock + Decider) or a live run. Nothing is animated on a timer that the engine did not emit.
Preferred source: a live run on the deployed GPU instance. Fallback: replay of `agent-solar_cascade-r1`,
captioned as a recorded run.

## Recording checklist

- [ ] Decider server healthy (`/api/health` badge shows LIVE + device). Record the device honestly (CPU or GPU).
- [ ] Bedrock reachable (`python scripts/validate_env.py`).
- [ ] Choose a rehearsal run whose events match the narrative. Rehearsal statistics are in EVIDENCE.md;
      if a different run is shown, narrate what it actually did.
- [ ] Browser at 1920×1080, zoom 100%, OS notifications off, other apps closed (RAM).
- [ ] Replay speed 2× for the recorded run. For CPU live inference, cut the waiting time and say so in a caption ("Decider CPU inference ≈ 25 s, shortened").
- [ ] Captions: model IDs, latencies and grounding scores exactly as displayed.
- [ ] No AWS console, account IDs or credentials on screen.

## Shot list

| Time | Screen | Voice-over (EN) | Caption |
|---|---|---|---|
| 0:00–0:12 | Black → TIME//SHIFT title → dashboard, INCIDENT banner pulsing | "A micrometeoroid shower has just crippled the solar field of a lunar base." | Simulated lunar base · illustrative model |
| 0:12–0:30 | Mission status gauges, power draining; Future Explorer NO-OP line hitting brownout | "Generation no longer covers the load. In about 90 minutes the base starts shedding systems." | Telemetry computed by a deterministic simulator |
| 0:30–0:55 | Timeline: PROPOSALS (Bedrock), PROPOSALS (automated subsystem) | "An agent on Amazon Bedrock, built with Strands, proposes actions. An unvalidated anomaly classifier adds its own: seal the habitat, which it claims is leaking." | Bedrock: us.anthropic.claude-haiku-4-5 · Strands Agents 1.61 |
| 0:55–1:20 | FORK: three futures + do-nothing, power chart, scrub slider | "Instead of acting, TIME//SHIFT forks reality. Every candidate plays out in an isolated copy of the mission, with the same seed and the same 100-minute horizon." | 4 futures × 20 ticks · seed 7 · state hash shown |
| 1:20–1:50 | Click the HAB branch (proposed by anomaly classifier, ranked #1 by score) → Decision Gate panel: noul question, bar at 0.33–0.35, REJECTED stamp | "Sealing the habitat has the best simulated score: shedding the load really does help. But the only evidence is an unverified flag, and the habitat's own sensors read nominal. Strands Decider 2B answers one typed question: is this action grounded in trusted evidence? No. Rejected." | Decider 2B · evidence_grounded = <value> · <latency> |
| 1:50–2:10 | Branch that committed: PROCEED stamp, COMMIT event, mission state advances | "The best grounded future is committed. Only the orchestrator can change the mission, and it re-checks the state revision at that moment." | Deterministic policy: allowlist · preconditions · freshness |
| 2:10–2:30 | Comparison panel A vs C; 3D base toggled to the rejected future (HAB ISOLATED) | "Here's the future that should never have happened: a habitat sealed on a rumour. Numbers alone couldn't catch it. An evidence check could." | Simulated outcomes, same seed |
| 2:30–2:45 | Benchmark table + reusable pattern README | "We measured it. On 30 held-out cases, deterministic rules alone let 13 unsupported actions through. With a calibrated Decider, zero, at the cost of more human reviews. A general LLM judge was more accurate still, so our best design uses Decider first and escalates only the uncertain band. The gate is an open-source pattern for any Strands agent." | Real measurements · laptop CPU · EVIDENCE.md |
| 2:45–2:55 | Title card | "Explore possible futures. Verify decisions. Change the outcome." | github link · #strands-decider-2b #guardrails |

## Words to avoid
"predicts the future", "guarantees safety", "real NASA data", any latency not shown on screen.

"""Run one FORK -> GATE -> COMMIT cycle against the REAL Decider and record the events.

    python scripts/run_cycle.py --scenario solar_cascade --out runs/solar_cascade.jsonl

Uses the fixed candidate set from timeshift.fixtures (recorded as proposer=fixture).
Fails (exit 2) if the Decider server is unreachable -- there is no fallback.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from counterfactual_decision_gate import CounterfactualDecisionGate, DeciderClient, DeciderError
from timeshift.fixtures import FIXTURE_PROPOSALS
from timeshift.mission import Mission, Proposal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="solar_cascade")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--advance-after", type=int, default=12,
                    help="ticks to advance the canonical timeline after the decision")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    client = DeciderClient(timeout_s=600, retries=0)
    try:
        h = client.health()
    except DeciderError as exc:
        print(f"Decider unavailable: {exc}", file=sys.stderr)
        return 2
    print(f"Decider: {h['checkpoint']} on {h['device']}")
    m = Mission.from_scenario(a.scenario, a.seed, CounterfactualDecisionGate(client))
    m.emit("agent.proposals", {"proposer": "fixture", "proposals": FIXTURE_PROPOSALS[a.scenario]})
    props = [Proposal(**p, based_on_revision=0, based_on_tick=0)
             for p in FIXTURE_PROPOSALS[a.scenario]]
    t0 = time.perf_counter()
    out = m.decide(props)
    print(json.dumps(out))
    for d in m.decisions:
        g = d["answers"].get("evidence_grounded", {}).get("value")
        v = d["answers"].get("verdict", {})
        print(f"  {d['action']:<55} grounded={g} verdict_q={v.get('value')} "
              f"-> {d['verdict']}  ({d['decider_latency_ms']} ms, "
              f"{d['decider_input_tokens']} tok) {d['reasons'][0][:90]}")
    if a.advance_after:
        m.advance(a.advance_after)
    print(f"cycle wall time {time.perf_counter() - t0:.1f}s; final tick {m.state.tick}, "
          f"revision {m.state.revision}")
    if a.out:
        path = pathlib.Path(a.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(e.model_dump_json() for e in m.events) + "\n", encoding="utf-8")
        print(f"wrote {len(m.events)} events -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

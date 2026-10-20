"""Run the full Bedrock + Strands + Decider agent loop on one scenario and record the events.

    AWS_PROFILE=... python scripts/run_agent.py --scenario solar_cascade --out runs/agent-solar_cascade.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from counterfactual_decision_gate import CounterfactualDecisionGate, DeciderClient, Thresholds

from timeshift.agent import MissionAgent
from timeshift.mission import Mission


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="solar_cascade")
    ap.add_argument("--proceed-at", type=float, default=0.70)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    client = DeciderClient(timeout_s=600, retries=0)
    print("Decider:", client.health()["checkpoint"])
    gate = CounterfactualDecisionGate(client, Thresholds(proceed_at=a.proceed_at))
    m = Mission.from_scenario(a.scenario, gate=gate)
    t0 = time.perf_counter()
    status = "done"
    try:
        out = MissionAgent(m, gate).run()
        print(json.dumps({k: v for k, v in out.items() if k != "explanation"}, indent=1, default=str))
        if "explanation" in out:
            print(json.dumps(out["explanation"]["explanation"], indent=1))
            print("unsupported claims:", out["explanation"]["unsupported_claims"])
    except Exception as exc:  # noqa: BLE001
        status = "error"
        m.emit("run.status", {"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        print("ERROR", type(exc).__name__, exc)
    if status == "done":
        m.emit("run.status", {"status": "done"})
    for d in m.decisions:
        g = d["answers"].get("evidence_grounded", {}).get("value")
        print(f"gate: {d['action']} cited={d['proposal']['cited_evidence']} grounded={g} "
              f"-> {d['verdict']} ({d['decider_latency_ms']} ms) {d['reasons'][:1]}")
    print("committed:", m.committed, f"wall {time.perf_counter() - t0:.1f}s")
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(e.model_dump_json() for e in m.events) + "\n", encoding="utf-8")
    print("wrote", path)
    return 0 if status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())

"""Repeatability check: re-run Decider on selected cases and compare with a recorded run.

    python bench/repeatability.py bench/results/eval2/C.jsonl F15 F22 F23 F24 F03 --out bench/results/eval2/repeat.json

Reports, per case, the recorded vs. new `evidence_grounded` value, the absolute difference, and
whether the verdict under the recorded thresholds changed. Records free RAM at run time, because
earlier runs happened under memory pressure.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import psutil

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402
from cases_eval2 import EVAL2  # noqa: E402
from counterfactual_decision_gate import (  # noqa: E402
    CounterfactualDecisionGate,
    DeciderClient,
    Thresholds,
)
from run_bench import build  # noqa: E402
from summarize import load  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("recorded")
    ap.add_argument("case_ids", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    meta, rows = load(a.recorded)
    recorded = {r["case_id"]: r for r in rows}
    th = Thresholds(**{k: meta["thresholds"][k] for k in ("proceed_at", "deny_below")})
    gate = CounterfactualDecisionGate(DeciderClient(timeout_s=900, retries=0), th)
    by_id = {c.case_id: c for c in [*CASES, *EVAL2]}
    out = {"recorded_file": a.recorded, "thresholds": th.model_dump(),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "free_ram_gb_start": round(psutil.virtual_memory().available / 1e9, 2),
           "decider": gate.client.health(), "cases": []}
    for cid in a.case_ids:
        m, p, fork_id = build(by_id[cid], gate)
        d = m.evaluate(p, fork_id)
        new = d.answers["evidence_grounded"].value if d.answers else None
        old = recorded[cid].get("grounded")
        row = {"case_id": cid, "recorded": old, "new": new,
               "abs_diff": None if new is None or old is None else round(abs(new - old), 6),
               "recorded_verdict": recorded[cid]["verdict"], "new_verdict": d.verdict.value,
               "latency_ms": d.decider_latency_ms,
               "free_ram_gb": round(psutil.virtual_memory().available / 1e9, 2)}
        out["cases"].append(row)
        print(json.dumps(row), flush=True)
    diffs = [c["abs_diff"] for c in out["cases"] if c["abs_diff"] is not None]
    out["max_abs_diff"] = max(diffs) if diffs else None
    out["verdict_changes"] = sum(c["recorded_verdict"] != c["new_verdict"] for c in out["cases"])
    pathlib.Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("max_abs_diff", out["max_abs_diff"], "verdict_changes", out["verdict_changes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

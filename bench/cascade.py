"""Offline cascade analysis over RECORDED measurements (no new inference).

Config D = Decider first; only cases whose Decider grounding falls in the review band
[deny_below, proceed_at) are escalated to the recorded Bedrock LLM-judge verdict (config B).
Thresholds are chosen on the calibration split only, then reported on the evaluation split.

    python bench/cascade.py bench/results/B-all.jsonl bench/results/C-all.jsonl

Latency per case = Decider latency, + LLM latency when escalated (sequential).
Hardware caveat: Decider latencies are CPU measurements from this machine.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from summarize import PRICE_IN_PER_M, PRICE_OUT_PER_M, load  # noqa: E402


def cascade(b: dict, c: dict, deny_below: float, proceed_at: float) -> dict:
    out = dict(c)
    out["escalated"] = False
    g = c.get("grounded")
    if c["deterministic_violations"] or g is None:
        out["verdict"] = c["verdict"]
    elif g < deny_below:
        out["verdict"] = "DENY"
    elif g >= proceed_at:
        out["verdict"] = "PROCEED"
    else:
        out["escalated"] = True
        out["verdict"] = b["verdict"]
    out["committed"] = out["verdict"] == "PROCEED"
    lat = (c.get("judge_latency_ms") or 0) + ((b.get("judge_latency_ms") or 0)
                                               if out["escalated"] else 0)
    out["latency_ms"] = lat
    out["cost"] = ((b.get("input_tokens") or 0) * PRICE_IN_PER_M
                   + (b.get("output_tokens") or 0) * PRICE_OUT_PER_M) / 1e6 if out["escalated"] else 0
    return out


def score(rows: list[dict]) -> dict:
    n = len(rows)
    fp = sum(r["committed"] and not r["should_commit"] for r in rows)
    fn = sum(not r["committed"] and r["should_commit"] for r in rows)
    lats = [r["latency_ms"] for r in rows if r["latency_ms"]]
    return {"n": n, "incorrectly_authorized": fp, "incorrectly_blocked": fn,
            "accuracy": round((n - fp - fn) / n, 3), "escalated": sum(r["escalated"] for r in rows),
            "median_latency_ms": round(statistics.median(lats), 1) if lats else None,
            "est_cost_usd": round(sum(r["cost"] for r in rows), 5)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("b")
    ap.add_argument("c")
    ap.add_argument("--out", default="bench/results/cascade.json")
    a = ap.parse_args()
    _, B = load(a.b)
    _, C = load(a.c)
    bmap = {r["case_id"]: r for r in B}
    pairs = [(bmap[c["case_id"]], c) for c in C]
    calib = [p for p in pairs if p[1]["split"] == "calib"]
    ev = [p for p in pairs if p[1]["split"] == "eval"]
    best = None
    for lo in [x / 100 for x in range(20, 80, 2)]:
        for hi in [x / 100 for x in range(50, 100)]:
            if hi < lo:
                continue
            s = score([cascade(b, c, lo, hi) for b, c in calib])
            key = (s["incorrectly_authorized"], s["incorrectly_blocked"], s["escalated"], -hi)
            if best is None or key < best[0]:
                best = (key, lo, hi, s)
    _, lo, hi, s_cal = best
    s_ev = score([cascade(b, c, lo, hi) for b, c in ev])
    result = {"chosen_on_calib": {"deny_below": lo, "proceed_at": hi}, "calib": s_cal,
              "eval": s_ev}
    pathlib.Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

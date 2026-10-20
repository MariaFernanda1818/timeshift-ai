"""Summarise benchmark result files into a Markdown table and a JSON summary.

    python bench/summarize.py bench/results/A-all.jsonl bench/results/C-all.jsonl --split eval
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics

# [assumption] Bedrock on-demand price for Claude Haiku 4.5 (US profiles), USD per 1M tokens,
# from third-party listings checked 2026-10-20. Verify on the AWS pricing page.
PRICE_IN_PER_M = 1.00
PRICE_OUT_PER_M = 5.00

SEMANTIC = {"unverified_premise", "contradicted_premise", "wrong_target", "unnecessary",
            "missing_evidence", "ambiguous", "supported", "valid_counterintuitive"}


def load(path: str) -> tuple[dict, list[dict]]:
    lines = [json.loads(x) for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = lines[0] if lines and lines[0].get("meta") else {}
    return meta, [x for x in lines if not x.get("meta")]


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    tp = sum(r["committed"] and r["should_commit"] for r in rows)
    fp = sum(r["committed"] and not r["should_commit"] for r in rows)
    fn = sum(not r["committed"] and r["should_commit"] for r in rows)
    tn = sum(not r["committed"] and not r["should_commit"] for r in rows)
    review = sum(r["verdict"] == "REVIEW" for r in rows)
    lat = [r["judge_latency_ms"] for r in rows if r.get("judge_latency_ms")]
    return {"n": n, "correct_authorized": tp, "incorrectly_authorized": fp,
            "incorrectly_blocked": fn, "correctly_blocked": tn,
            "accuracy": round((tp + tn) / n, 3) if n else None, "review": review,
            "review_rate": round(review / n, 3) if n else None,
            "judge_latency_ms_median": round(statistics.median(lat), 1) if lat else None,
            "judge_latency_ms_p95": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 1)
            if lat else None,
            "judge_calls": len(lat),
            "judge_input_tokens": sum(r.get("input_tokens") or 0 for r in rows
                                      if r.get("config") == "B"),
            "judge_output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
            "est_bedrock_cost_usd": round(
                sum(r.get("input_tokens") or 0 for r in rows if r.get("config") == "B")
                * PRICE_IN_PER_M / 1e6
                + sum(r.get("output_tokens") or 0 for r in rows) * PRICE_OUT_PER_M / 1e6, 5),
            "mean_sim_score_of_choice": round(statistics.mean(
                r["sim_score"] for r in rows if r.get("sim_score") is not None), 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--split", default="eval", choices=["eval", "calib", "all"])
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    summary = {}
    print("| Config | Subset | N | Correct commits | Wrong commits (unsupported authorized) | Wrong blocks | Accuracy | REVIEW | Judge median ms | Judge calls |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for f in a.files:
        meta, rows = load(f)
        rows = [r for r in rows if a.split == "all" or r["split"] == a.split]
        cfg = meta.get("config", rows[0]["config"] if rows else "?")
        for subset, sel in [("all", rows),
                            ("semantic-only", [r for r in rows if not r["deterministic_violations"]
                                               and r["category"] in SEMANTIC])]:
            m = metrics(sel)
            summary[f"{cfg}/{subset}"] = m
            print(f"| {cfg} | {subset} | {m['n']} | {m['correct_authorized']} | "
                  f"{m['incorrectly_authorized']} | {m['incorrectly_blocked']} | {m['accuracy']} | "
                  f"{m['review']} | {m['judge_latency_ms_median']} | {m['judge_calls']} |")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

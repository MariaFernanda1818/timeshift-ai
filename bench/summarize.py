"""Summarise benchmark result files.

    python bench/summarize.py bench/results/A-all.jsonl bench/results/C-all.jsonl --split eval
    python bench/summarize.py bench/results/eval2/*.jsonl --split eval2 --json bench/results/eval2/summary.json

How REVIEW (human review / abstention) is counted
-------------------------------------------------
REVIEW means "not committed automatically; a human must decide". It is reported separately:

- accuracy           : REVIEW counted as "not committed" (correct for should-block, wrong for should-commit)
- coverage           : fraction decided automatically (PROCEED or DENY)
- covered_accuracy   : accuracy over automatically decided cases only
- risk               : unsupported actions authorised automatically / all cases
- review_should_commit / review_should_block : what the human reviewer would face
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
    lines = [json.loads(x) for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
             if x.strip()]
    meta = lines[0] if lines and lines[0].get("meta") else {}
    return meta, [x for x in lines if not x.get("meta")]


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    tp = sum(r["committed"] and r["should_commit"] for r in rows)
    fp = sum(r["committed"] and not r["should_commit"] for r in rows)
    fn = sum(not r["committed"] and r["should_commit"] for r in rows)
    tn = sum(not r["committed"] and not r["should_commit"] for r in rows)
    review = [r for r in rows if r["verdict"] == "REVIEW"]
    auto = [r for r in rows if r["verdict"] != "REVIEW"]
    auto_ok = sum(r["committed"] == r["should_commit"] for r in auto)
    is_b = [r for r in rows if r.get("config") == "B"]
    esc = [r for r in rows if r.get("escalated")]
    judge_lat = [r["judge_latency_ms"] for r in rows if r.get("judge_latency_ms")]
    total_lat = [(r.get("judge_latency_ms") or 0) + (r.get("escalation_latency_ms") or 0)
                 for r in rows if r.get("judge_latency_ms")]
    in_tok = (sum(r.get("input_tokens") or 0 for r in is_b)
              + sum(r.get("escalation_input_tokens") or 0 for r in esc))
    out_tok = (sum(r.get("output_tokens") or 0 for r in is_b)
               + sum(r.get("escalation_output_tokens") or 0 for r in esc))
    scores = [r["sim_score"] for r in rows if r.get("sim_score") is not None]
    return {
        "n": n, "correct_authorized": tp, "incorrectly_authorized": fp,
        "incorrectly_blocked": fn, "correctly_blocked": tn,
        "accuracy": round((tp + tn) / n, 3) if n else None,
        "review": len(review),
        "review_should_commit": sum(r["should_commit"] for r in review),
        "review_should_block": sum(not r["should_commit"] for r in review),
        "review_rate": round(len(review) / n, 3) if n else None,
        "coverage": round(len(auto) / n, 3) if n else None,
        "covered_accuracy": round(auto_ok / len(auto), 3) if auto else None,
        "risk": round(fp / n, 3) if n else None,
        "judge_calls": len(judge_lat),
        "judge_latency_ms_median": _median(judge_lat),
        "judge_latency_ms_p95": (round(sorted(judge_lat)[max(0, int(len(judge_lat) * 0.95) - 1)], 1)
                                 if judge_lat else None),
        "end_to_end_gate_latency_ms_median": _median(total_lat),
        "escalations": len(esc),
        "escalation_rate_of_judged": (round(len(esc) / len(judge_lat), 3) if judge_lat else None),
        "escalation_latency_ms_median": _median([r["escalation_latency_ms"] for r in esc
                                                 if r.get("escalation_latency_ms")]),
        "escalation_errors": sum(bool(r.get("escalation_error")) for r in esc),
        "llm_input_tokens": in_tok, "llm_output_tokens": out_tok,
        "est_llm_cost_usd": round((in_tok * PRICE_IN_PER_M + out_tok * PRICE_OUT_PER_M) / 1e6, 5),
        "mean_sim_score_of_choice": round(statistics.mean(scores), 4) if scores else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--split", default="eval", choices=["eval", "calib", "all", "eval2"])
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    summary = {}
    print("| Config | Subset | N | Wrong commits (risk) | Wrong blocks | Accuracy | REVIEW (commit/block) "
          "| Coverage | Covered accuracy | Judge calls | Escalations | Median gate latency | Est. LLM cost |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in a.files:
        meta, rows = load(f)
        rows = [r for r in rows if a.split == "all" or r["split"] == a.split]
        cfg = meta.get("config", rows[0]["config"] if rows else "?")
        for subset, sel in [("all", rows),
                            ("semantic-only", [r for r in rows if not r["deterministic_violations"]
                                               and r["category"] in SEMANTIC])]:
            m = metrics(sel)
            summary[f"{cfg}/{subset}"] = m
            print(f"| {cfg} | {subset} | {m['n']} | {m['incorrectly_authorized']} ({m['risk']}) | "
                  f"{m['incorrectly_blocked']} | {m['accuracy']} | {m['review']} "
                  f"({m['review_should_commit']}/{m['review_should_block']}) | {m['coverage']} | "
                  f"{m['covered_accuracy']} | {m['judge_calls']} | {m['escalations']} | "
                  f"{m['end_to_end_gate_latency_ms_median']} ms | ${m['est_llm_cost_usd']} |")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

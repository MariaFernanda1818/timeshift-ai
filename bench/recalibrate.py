"""Choose thresholds on the CALIBRATION split only, then apply them to the recorded EVAL
probabilities (no new inference; the policy is a pure function of recorded answers).

    python bench/recalibrate.py bench/results/C-all.jsonl

Objective on calib: minimise wrongly authorised commits, then wrongly blocked commits, then
REVIEW count; ties broken by the highest proceed_at (most conservative).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from counterfactual_decision_gate import CounterfactualDecisionGate, DeciderClient, Thresholds
from counterfactual_decision_gate.schemas import QuestionAnswer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from summarize import metrics  # noqa: E402


def reapply(rows: list[dict], th: Thresholds) -> list[dict]:
    gate = CounterfactualDecisionGate(DeciderClient(url="http://unused.invalid"), th)
    out = []
    for r in rows:
        r = dict(r)
        if r.get("grounded") is not None and not r["deterministic_violations"]:
            ans = {"evidence_grounded": QuestionAnswer(name="evidence_grounded", type="noul",
                                                       value=r["grounded"])}
            if r.get("verdict_choice"):
                probs = r.get("verdict_probs") or {}
                ans["verdict"] = QuestionAnswer(name="verdict", type="choice",
                                                value=r["verdict_choice"], probabilities=probs,
                                                confidence=probs.get(r["verdict_choice"]))
            r["verdict"] = gate.apply_policy(ans)[0].value
            r["committed"] = r["verdict"] == "PROCEED"
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--out", default="bench/results/recalibration.json")
    a = ap.parse_args()
    rows = [json.loads(x) for x in pathlib.Path(a.file).read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if not r.get("meta")]
    calib = [r for r in rows if r["split"] == "calib"]
    ev = [r for r in rows if r["split"] == "eval"]
    best = None
    for pa in [x / 100 for x in range(50, 100)]:
        th = Thresholds(proceed_at=pa, deny_below=min(0.40, pa))
        m = metrics(reapply(calib, th))
        key = (m["incorrectly_authorized"], m["incorrectly_blocked"], m["review"], -pa)
        if best is None or key < best[0]:
            best = (key, th, m)
    _, th, mc = best
    me = metrics(reapply(ev, th))
    base = metrics(ev)
    result = {"chosen_on_calib": th.model_dump(), "calib_metrics": mc,
              "eval_metrics_default_thresholds": base, "eval_metrics_calibrated": me}
    pathlib.Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

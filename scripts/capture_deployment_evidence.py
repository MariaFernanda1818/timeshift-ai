"""Capture deployment evidence through the app's own API (no shell access to the instance needed).

With an SSM port forward to the instance on localhost:8080:

    python scripts/capture_deployment_evidence.py --base http://127.0.0.1:8080 \
        --proposer bedrock --label aws-m7i-flex --out docs/deployment

Saves: the /api/health JSON (Decider checkpoint + device as reported by the server running on the
instance), the full event log of one real mission run, and a summary with the Decider latencies,
verdicts, committed action and Bedrock usage taken from those events. Nothing is synthesised.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.request


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--scenario", default="solar_cascade")
    ap.add_argument("--proposer", choices=["bedrock", "fixture"], default="bedrock")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", default="docs/deployment")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    health = get(f"{a.base}/api/health")
    (out / f"{a.label}-{stamp}-health.json").write_text(json.dumps(health, indent=2), encoding="utf-8")
    print("health:", json.dumps(health.get("decider", {}))[:200])

    body = json.dumps({"scenario": a.scenario, "proposer": a.proposer, "advance_after": 6}).encode()
    req = urllib.request.Request(f"{a.base}/api/missions", data=body,
                                 headers={"content-type": "application/json"})
    mid = json.loads(urllib.request.urlopen(req, timeout=30).read())["mission_id"]
    print("mission:", mid)
    t0 = time.time()
    events = []
    with urllib.request.urlopen(f"{a.base}/api/missions/{mid}/events", timeout=3600) as stream:
        for raw in stream:
            line = raw.decode().strip()
            if not line.startswith("data:") or line[5:].strip() == "{}":
                continue
            ev = json.loads(line[5:])
            events.append(ev)
            print(f"{time.time() - t0:7.1f}s {ev['type']}", flush=True)
            if ev["type"] == "run.status" and ev["payload"].get("status") in ("done", "error",
                                                                               "awaiting_review"):
                break
    (out / f"{a.label}-{stamp}-events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    decisions = [e["payload"] for e in events if e["type"] == "gate.decision"]
    finished = next((e["payload"] for e in events if e["type"] == "agent.finished"), {})
    summary = {
        "label": a.label, "captured_at": stamp, "base": a.base, "mission_id": mid,
        "proposer": a.proposer, "wall_s": round(time.time() - t0, 1),
        "decider": {k: health.get("decider", {}).get(k) for k in ("checkpoint", "device", "status")},
        "decisions": [{"action": d["action"], "verdict": d["verdict"],
                       "evidence_grounded": (d["answers"].get("evidence_grounded") or {}).get("value"),
                       "decider_latency_ms": d["decider_latency_ms"],
                       "decider_status": d["decider_status"]} for d in decisions],
        "committed": [e["payload"]["proposal"]["tool"] for e in events
                      if e["type"] == "action.committed"],
        "bedrock_usage": finished.get("usage"),
        "final_status": next((e["payload"].get("status") for e in reversed(events)
                              if e["type"] == "run.status"), None),
    }
    (out / f"{a.label}-{stamp}-summary.json").write_text(json.dumps(summary, indent=2),
                                                        encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["final_status"] in ("done", "awaiting_review") else 1


if __name__ == "__main__":
    raise SystemExit(main())

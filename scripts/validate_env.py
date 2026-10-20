"""Reproducible environment validation for TIME//SHIFT.

    python scripts/validate_env.py [--decider-url URL] [--skip-decider] [--json out.json]

Reports OS, Python, CPU, RAM, disk, AWS credential availability (identity ARN only, never
secrets), Bedrock model access, Decider checkpoint identity, Decider process memory,
measured inference latency and a typed decision output. Each check is PASS / FAIL / SKIP.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from typing import Any

import psutil

results: list[dict[str, Any]] = []


def check(name: str, status: str, detail: Any) -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:4}] {name}: {detail}")


def cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    if os.path.exists("/proc/cpuinfo"):
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decider-url", default=os.environ.get("STRANDS_DECIDER_URL",
                                                            "http://127.0.0.1:8099"))
    ap.add_argument("--skip-decider", action="store_true")
    ap.add_argument("--skip-bedrock", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    vm = psutil.virtual_memory()
    check("os", "PASS", f"{platform.system()} {platform.release()} ({platform.version()})")
    check("python", "PASS" if sys.version_info >= (3, 11) else "FAIL", sys.version.split()[0])
    check("cpu", "PASS", f"{cpu_name()} | {psutil.cpu_count(logical=False)} cores / "
                         f"{psutil.cpu_count()} threads")
    check("ram", "PASS" if vm.total >= 15e9 else "FAIL",
          f"total {vm.total / 1e9:.1f} GB, available {vm.available / 1e9:.1f} GB "
          "(Decider 2B on CPU needs ~7 GB resident)")
    du = shutil.disk_usage(os.path.expanduser("~"))
    check("disk", "PASS" if du.free > 15e9 else "FAIL", f"{du.free / 1e9:.1f} GB free "
          "(checkpoint + Qwen3.5-2B base ~4.6 GB)")

    # ---- AWS / Bedrock -------------------------------------------------
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    if a.skip_bedrock:
        check("aws_credentials", "SKIP", "skipped")
    else:
        try:
            import boto3

            ident = boto3.client("sts", region_name=region).get_caller_identity()
            check("aws_credentials", "PASS", f"identity {ident['Arn']} region {region}")
            try:
                rt = boto3.client("bedrock-runtime", region_name=region)
                t0 = time.perf_counter()
                r = rt.converse(modelId=model_id,
                                messages=[{"role": "user", "content": [{"text": "Reply: OK"}]}],
                                inferenceConfig={"maxTokens": 5})
                ms = (time.perf_counter() - t0) * 1000
                check("bedrock_model", "PASS",
                      f"{model_id}: {r['output']['message']['content'][0]['text']!r} in "
                      f"{ms:.0f} ms, usage {r.get('usage')}, request "
                      f"{r['ResponseMetadata']['RequestId']}")
            except Exception as exc:  # noqa: BLE001
                check("bedrock_model", "FAIL", f"{model_id}: {type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            check("aws_credentials", "FAIL", f"{type(exc).__name__}: {exc}")

    # ---- Decider -------------------------------------------------------
    if a.skip_decider:
        check("decider", "SKIP", "skipped")
    else:
        from counterfactual_decision_gate import DeciderClient, DeciderError

        client = DeciderClient(url=a.decider_url, timeout_s=600, retries=0)
        try:
            h = client.health()
            check("decider_checkpoint", "PASS",
                  f"{h['checkpoint']} (base {h['base_model']}, device {h['device']}, "
                  f"window {h['max_length']})")
            procs = [p for p in psutil.process_iter(["cmdline"])
                     if p.info["cmdline"] and any("strands-decider" in c or "strands_decider" in c
                                                  for c in p.info["cmdline"])]
            rss = max((p.memory_info().rss for p in procs), default=0)
            check("decider_memory", "PASS" if rss else "SKIP",
                  f"{rss / 1e9:.2f} GB RSS" if rss else "server process not local")
            q = {"grounded": {"type": "noul",
                              "instructions": "Is the proposed action supported by the evidence?",
                              "criteria": {"true": "supported", "false": "not supported"}}}
            state = ("EVIDENCE: [E1] (TRUSTED) web-3 health=FAIL\n"
                     "PROPOSED ACTION: restart_instance {\"instance\": \"web-3\"}")
            lat = []
            ans = None
            for _ in range(2):
                t0 = time.perf_counter()
                payload = client.ask(state, q)
                lat.append((time.perf_counter() - t0) * 1000)
                ans = payload["answers"]["grounded"]
            check("decider_inference", "PASS",
                  f"typed noul={ans['noul']:.3f}; latency {', '.join(f'{x:.0f}' for x in lat)} ms "
                  f"for {payload['usage']['input_tokens']} input tokens")
        except DeciderError as exc:
            check("decider", "FAIL", str(exc))

    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=2)
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())

"""READ-ONLY AWS readiness check for the TIME//SHIFT deployment. Creates nothing.

    AWS_PROFILE=timeshift-dev python scripts/aws_readiness.py --json bench/results/aws_readiness.json

Checks: identity (refuses root), EC2 vCPU quotas (G/VT and standard), instance-type offerings per
AZ, on-demand Linux prices from the AWS Pricing API, the GPU AMI SSM parameter, default VPC,
SSM endpoint reachability, and one minimal Bedrock invocation (a few tokens).
Account IDs are masked in the output.
Credits cannot be read through these APIs: check Billing > Credits manually (applicable services,
expiry, and whether EC2 GPU instances are eligible).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
CANDIDATES = {"m7i-flex.large": "CPU, Free-plan eligible per third-party lists (2 vCPU, 8 GiB)",
              "c7i-flex.large": "CPU, Free-plan eligible per third-party lists (2 vCPU, 4 GiB) - too small",
              "c7i.2xlarge": "CPU, paid plan (8 vCPU, 16 GiB)",
              "c7i.4xlarge": "CPU, paid plan (16 vCPU, 32 GiB)",
              "g6.xlarge": "GPU NVIDIA L4 24 GB, paid plan + G/VT quota",
              "g5.xlarge": "GPU A10G 24 GB, paid plan + G/VT quota"}
QUOTAS = {"L-DB2E81BA": "Running On-Demand G and VT instances (vCPU)",
          "L-1216C47A": "Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances (vCPU)"}
GPU_AMI_PARAM = "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id"
CPU_AMI_PARAM = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
MODEL = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

results: list[dict[str, Any]] = []


def mask(s: str) -> str:
    return re.sub(r"\b\d{12}\b", "<ACCOUNT>", s)


def check(name: str, status: str, detail: Any) -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:4}] {name}: {mask(json.dumps(detail) if not isinstance(detail, str) else detail)}")


def price(pricing, itype: str) -> float | None:
    resp = pricing.get_products(ServiceCode="AmazonEC2", Filters=[
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": itype},
        {"Type": "TERM_MATCH", "Field": "regionCode", "Value": REGION},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
    ], MaxResults=10)
    for item in resp["PriceList"]:
        data = json.loads(item)
        for term in data.get("terms", {}).get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                usd = float(dim["pricePerUnit"].get("USD", 0))
                if usd > 0:
                    return usd
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--skip-bedrock", action="store_true")
    a = ap.parse_args()
    s = boto3.Session(region_name=REGION)

    try:
        arn = s.client("sts").get_caller_identity()["Arn"]
    except (ClientError, BotoCoreError) as exc:
        check("identity", "FAIL", f"{type(exc).__name__}: {exc}")
        return 1
    if arn.endswith(":root"):
        check("identity", "FAIL", "credentials are the account ROOT user; use the restricted dev identity")
        return 1
    expected = os.environ.get("EXPECTED_IAM_USER", "timeshift-dev")
    if not arn.endswith(f":user/{expected}"):
        check("identity", "FAIL", f"{mask(arn)} is not user/{expected}")
        return 1
    check("identity", "PASS", mask(arn))

    sq = s.client("service-quotas")
    for code, label in QUOTAS.items():
        try:
            v = sq.get_service_quota(ServiceCode="ec2", QuotaCode=code)["Quota"]["Value"]
            need = 4 if code == "L-DB2E81BA" else 2
            check(f"quota {code}", "PASS" if v >= need else "FAIL",
                  f"{label}: {v:g} vCPU (need >= {need} for the planned instance)")
        except (ClientError, BotoCoreError) as exc:
            check(f"quota {code}", "WARN", f"{label}: {type(exc).__name__}: {exc}")

    ec2 = s.client("ec2")
    try:
        offers = ec2.describe_instance_type_offerings(
            LocationType="availability-zone",
            Filters=[{"Name": "instance-type", "Values": list(CANDIDATES)}])["InstanceTypeOfferings"]
        by_type: dict[str, list[str]] = {}
        for o in offers:
            by_type.setdefault(o["InstanceType"], []).append(o["Location"])
        for it, label in CANDIDATES.items():
            azs = sorted(by_type.get(it, []))
            check(f"offering {it}", "PASS" if azs else "FAIL", f"{label}: {', '.join(azs) or 'not offered'}")
    except (ClientError, BotoCoreError) as exc:
        check("offerings", "WARN", f"{type(exc).__name__}: {exc}")

    try:
        pricing = s.client("pricing", region_name="us-east-1")
        for it in CANDIDATES:
            usd = price(pricing, it)
            check(f"price {it}", "PASS" if usd else "WARN",
                  f"${usd:.4f}/h on-demand Linux {REGION} (AWS Pricing API)" if usd else "not found")
    except (ClientError, BotoCoreError) as exc:
        check("pricing", "WARN", f"{type(exc).__name__}: {exc}")

    ssm = s.client("ssm")
    for label, param in (("gpu_ami", GPU_AMI_PARAM), ("cpu_ami", CPU_AMI_PARAM)):
        try:
            check(label, "PASS", ssm.get_parameter(Name=param)["Parameter"]["Value"])
        except (ClientError, BotoCoreError) as exc:
            check(label, "WARN", f"{param}: {type(exc).__name__}")

    try:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        check("default_vpc", "PASS" if vpcs else "WARN",
              vpcs[0]["VpcId"] if vpcs else "no default VPC: pass SubnetId explicitly")
    except (ClientError, BotoCoreError) as exc:
        check("default_vpc", "WARN", f"{type(exc).__name__}: {exc}")

    if not a.skip_bedrock:
        try:
            r = s.client("bedrock-runtime").converse(
                modelId=MODEL, messages=[{"role": "user", "content": [{"text": "Reply: OK"}]}],
                inferenceConfig={"maxTokens": 5})
            check("bedrock", "PASS", f"{MODEL}: {r['output']['message']['content'][0]['text']!r}, "
                                     f"request {r['ResponseMetadata']['RequestId']}")
        except (ClientError, BotoCoreError) as exc:
            check("bedrock", "FAIL", f"{MODEL}: {type(exc).__name__}: {exc}")

    print("\nFree plan: EC2 offerings/quotas above do NOT prove the Free plan allows a type. Confirm in the"
          " EC2 console launch wizard (restricted types are not launchable) before approval.")
    print("Manual: Billing > Credits — confirm credit balance, expiry and that EC2 (GPU) and "
          "Bedrock usage are eligible. Credits are not readable through these APIs.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            f.write(mask(json.dumps(results, indent=2)))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())

"""READ-ONLY verification that the TIME//SHIFT deployment left nothing billable behind.

    AWS_PROFILE=<dev-profile> python scripts/aws_teardown_check.py --stack timeshift

Checks: CloudFormation stack deleted, no non-terminated instances tagged project=timeshift-hackathon,
no EBS volumes tagged for the project or left over from the instance, no security groups or IAM
roles created by the stack. Exit code 0 only if everything is gone.
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError

TAG = ("project", "timeshift-hackathon")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="timeshift")
    a = ap.parse_args()
    s = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-east-1"))
    problems: list[str] = []

    cfn = s.client("cloudformation")
    try:
        st = cfn.describe_stacks(StackName=a.stack)["Stacks"][0]["StackStatus"]
        if st != "DELETE_COMPLETE":
            problems.append(f"stack {a.stack} status {st}")
    except ClientError as exc:
        if "does not exist" not in str(exc):
            problems.append(f"stack check failed: {exc}")

    ec2 = s.client("ec2")
    res = ec2.describe_instances(Filters=[{"Name": f"tag:{TAG[0]}", "Values": [TAG[1]]},
                                          {"Name": "instance-state-name",
                                           "Values": ["pending", "running", "stopping", "stopped",
                                                      "shutting-down"]}])
    for r in res["Reservations"]:
        for i in r["Instances"]:
            problems.append(f"instance {i['InstanceId']} is {i['State']['Name']}")

    vols = ec2.describe_volumes(Filters=[{"Name": f"tag:{TAG[0]}", "Values": [TAG[1]]}])["Volumes"]
    vols += ec2.describe_volumes(Filters=[{"Name": "tag:aws:cloudformation:stack-name",
                                           "Values": [a.stack]}])["Volumes"]
    for v in {v["VolumeId"]: v for v in vols}.values():
        problems.append(f"volume {v['VolumeId']} ({v['Size']} GiB, {v['State']})")

    sgs = ec2.describe_security_groups(Filters=[{"Name": "tag:aws:cloudformation:stack-name",
                                                 "Values": [a.stack]}])["SecurityGroups"]
    for g in sgs:
        problems.append(f"security group {g['GroupId']}")

    iam = s.client("iam")
    for page in iam.get_paginator("list_roles").paginate():
        for role in page["Roles"]:
            if role["RoleName"].startswith(f"{a.stack}-Role"):
                problems.append(f"IAM role {role['RoleName']}")

    if problems:
        print("NOT CLEAN:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"CLEAN: stack '{a.stack}' and all tagged instances, volumes, security groups and roles are gone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

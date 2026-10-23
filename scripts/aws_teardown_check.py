"""READ-ONLY verification that a TIME//SHIFT deployment, a failed deployment or a rollback left
nothing billable behind. Never deletes anything; it prints the exact cleanup commands.

    python scripts/aws_teardown_check.py --profile timeshift-dev --stack timeshift

Does not assume CloudFormation cleaned up after a failure:
- stack state, including ROLLBACK_FAILED, DELETE_FAILED, UPDATE_ROLLBACK_FAILED and
  ROLLBACK_COMPLETE (a failed create that still has to be deleted);
- every stack resource whose status is not DELETE_COMPLETE, and the failure events with reasons;
- independently of the stack, any EC2 instance, EBS volume or security group tagged
  project=timeshift-hackathon or aws:cloudformation:stack-name=<stack>.
Exit code 0 only if everything is gone.
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError

TAG = ("project", "timeshift-hackathon")
NEEDS_ACTION = {
    "ROLLBACK_COMPLETE": "create failed and rolled back; the stack shell must still be deleted",
    "ROLLBACK_FAILED": "rollback could not delete some resources; inspect them, then delete-stack",
    "DELETE_FAILED": "deletion failed; fix the blocking resource, then retry delete-stack "
                     "(or --retain-resources only for resources you then delete manually)",
    "UPDATE_ROLLBACK_FAILED": "update rollback failed; continue-update-rollback or delete-stack",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="timeshift")
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    a = ap.parse_args()
    s = boto3.Session(profile_name=a.profile,
                      region_name=os.environ.get("AWS_REGION", "us-east-1"))
    problems: list[str] = []
    notes: list[str] = []

    cfn = s.client("cloudformation")
    status = None
    try:
        status = cfn.describe_stacks(StackName=a.stack)["Stacks"][0]["StackStatus"]
    except ClientError as exc:
        if "does not exist" not in str(exc):
            problems.append(f"stack check failed: {exc.response['Error']['Code']}")
    if status and status != "DELETE_COMPLETE":
        problems.append(f"stack {a.stack}: {status}"
                        + (f" -> {NEEDS_ACTION[status]}" if status in NEEDS_ACTION else ""))
        try:
            for r in cfn.describe_stack_resources(StackName=a.stack)["StackResources"]:
                if r["ResourceStatus"] != "DELETE_COMPLETE":
                    problems.append(f"  resource {r['LogicalResourceId']} ({r['ResourceType']}) "
                                    f"{r.get('PhysicalResourceId', '?')}: {r['ResourceStatus']}")
            for e in cfn.describe_stack_events(StackName=a.stack)["StackEvents"][:30]:
                if e["ResourceStatus"].endswith("FAILED"):
                    notes.append(f"  event {e['LogicalResourceId']} {e['ResourceStatus']}: "
                                 f"{e.get('ResourceStatusReason', '')[:200]}")
        except ClientError as exc:
            notes.append(f"  (stack resources/events not readable: {exc.response['Error']['Code']})")

    ec2 = s.client("ec2")
    live = ["pending", "running", "stopping", "stopped", "shutting-down"]
    selectors = (TAG, ("aws:cloudformation:stack-name", a.stack))
    for key, val in selectors:
        res = ec2.describe_instances(Filters=[{"Name": f"tag:{key}", "Values": [val]},
                                              {"Name": "instance-state-name", "Values": live}])
        for r in res["Reservations"]:
            for i in r["Instances"]:
                problems.append(f"instance {i['InstanceId']} is {i['State']['Name']} "
                                f"-> aws ec2 terminate-instances --instance-ids {i['InstanceId']}")
    vols: dict = {}
    sgs: dict = {}
    for key, val in selectors:
        flt = [{"Name": f"tag:{key}", "Values": [val]}]
        for v in ec2.describe_volumes(Filters=flt)["Volumes"]:
            vols[v["VolumeId"]] = v
        for g in ec2.describe_security_groups(Filters=flt)["SecurityGroups"]:
            sgs[g["GroupId"]] = g
    for v in vols.values():
        problems.append(f"volume {v['VolumeId']} ({v['Size']} GiB, {v['State']})"
                        + (f" -> aws ec2 delete-volume --volume-id {v['VolumeId']}"
                           if v["State"] == "available" else ""))
    for g in sgs.values():
        problems.append(f"security group {g['GroupId']} -> aws ec2 delete-security-group "
                        f"--group-id {g['GroupId']}")

    if problems:
        print("NOT CLEAN:")
        for p in problems + notes:
            print("  -", p)
        print("Cleanup order: delete-stack (or fix + retry) -> terminate instances -> delete "
              "available volumes -> delete security groups -> re-run this check.")
        return 1
    print(f"CLEAN: stack '{a.stack}' and all tagged instances, volumes and security groups are gone.")
    print("Reminder (owner, console): the stack creates no IAM resources. When the hackathon is over,"
          " delete the pre-created roles timeshift-cfn-role and timeshift-instance-role and detach"
          " timeshift-dev-deploy-temp from the group.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

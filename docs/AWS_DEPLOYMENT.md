# AWS deployment

**Status (2026-10-21): PREPARED, NOT PROVISIONED.** Nothing here has been run against AWS yet, except
the Bedrock invocations recorded in EVIDENCE.md. Provisioning needs (1) the restricted developer
identity, (2) a passing readiness check and (3) explicit owner approval.

## Architecture

```
operator laptop --SSM port forward (no inbound ports)--> EC2 (private by policy, public IP for egress only)
                                                          |-- uvicorn timeshift.server    127.0.0.1:8080
                                                          |-- strands-decider serve        127.0.0.1:8099  (no auth: never exposed)
                                                          '-- instance role --> Amazon Bedrock (one model only)
```

- One CloudFormation stack: [`deploy/cfn/timeshift.yaml`](../deploy/cfn/timeshift.yaml)
  (`cfn-lint` clean). It contains the instance, a security group with **no inbound rules** and egress
  limited to 443/80/53, IMDSv2 required, an encrypted gp3 root volume, and an instance role with
  `AmazonSSMManagedInstanceCore` plus InvokeModel on one Bedrock model.
- Setup script: [`deploy/ec2/user-data.sh`](../deploy/ec2/user-data.sh). It installs the app and Decider,
  then creates two systemd services (`DEVICE=cuda|cpu`).
- Suggested policy for the developer identity:
  [`deploy/iam/dev-identity-policy.json`](../deploy/iam/dev-identity-policy.json). It covers read-only
  readiness checks, one Bedrock model, this stack only, and SSM sessions to tagged project instances.
  Replace `ACCOUNT_ID`. *Not yet tested against IAM; validate with IAM Access Analyzer.*

## Why a GPU, and the CPU fallback

Measured on the laptop CPU (i5-1235U): Decider took 6.1 GB of RAM and ~30–45 s per gate call
(~1,300-token state). A full agent run took ~2 min. Upstream reports ~115 ms per question on an RTX
3090 (not measured by us).

| Option | Instance | Decider device | Expected behaviour | Status |
|---|---|---|---|---|
| Primary | g6.xlarge (1× L4 24 GB, 4 vCPU, 16 GiB) | cuda | sub-second to a few seconds per call (to be measured) | needs G/VT quota ≥ 4 vCPU |
| Alternate GPU | g5.xlarge (A10G 24 GB) | cuda | similar | same quota |
| CPU fallback | c7i.4xlarge (16 vCPU, 32 GiB) | cpu | likely tens of seconds per call (to be measured; must not be assumed faster than the laptop) | standard quota ≥ 16 vCPU |

If the GPU quota is not granted in time, we deploy the CPU fallback and present latency as
measured. The decision logic is identical on CPU and GPU (same checkpoint, same answers).

## Step 1: readiness (read-only, with the dev identity)

```bash
export AWS_PROFILE=<dev-profile> AWS_REGION=us-east-1
python scripts/aws_readiness.py --json bench/results/aws_readiness.json
```

It refuses to run with root credentials, then reports:
- EC2 quotas `L-DB2E81BA` (G/VT vCPU) and `L-1216C47A` (standard vCPU);
- per-AZ offerings for g6.xlarge, g5.xlarge, c7i.4xlarge and c7i.2xlarge;
- **current on-demand prices from the AWS Pricing API**;
- GPU and CPU AMI IDs from SSM public parameters;
- the default VPC;
- one minimal Bedrock call.

**Credits:** not readable via these APIs. Check *Billing → Credits* manually (balance, expiry, and
whether EC2 GPU instances and Bedrock are eligible services).

If the G/VT quota is below 4: `aws service-quotas request-service-quota-increase --service-code ec2
--quota-code L-DB2E81BA --desired-value 8` (free to request; approval can take hours or days).

## Step 2: cost estimate and the US$15 cap

**Planned spending cap: US$15** for deployment + testing, including storage, transfer and Bedrock.
This is a plan, not an authorisation: the owner approves the final numbers from Step 1.

| Item | Rate (replace with Pricing API values) | Planned usage | Estimate |
|---|---|---|---|
| g6.xlarge (GPU path) | ~$0.80/h | ≤ 12 h | ≤ $9.70 |
| *or* c7i.2xlarge (CPU fallback) | ~$0.36/h | ≤ 12 h | ≤ $4.30 |
| EBS gp3 100 GiB | ~$0.08/GiB-month | ≤ 2 days | ≤ $0.55 |
| Bedrock Claude Haiku 4.5 | ~$1 / $5 per M in/out tokens | ≤ 0.5 M in, 0.05 M out | ≤ $0.75 |
| Data transfer out (dashboard via SSM, model download is inbound/free) | ~$0.09/GB | ≤ 2 GB | ≤ $0.20 |
| Public IPv4 address | $0.005/h | ≤ 12 h | ≤ $0.06 |
| **GPU path total** | | | **≤ ~$11.30** |
| **CPU path total** | | | **≤ ~$5.90** |

Guardrails: an AWS Budget alert at $10 (actual) and $15 (forecast), owner-created; the instance is
stopped whenever idle; the stack is deleted right after the video is recorded. Under the cap, the GPU
path allows at most ~15 instance-hours in total.

## Step 3: deploy (ONLY after approval)

The repository must be public first (owner approval), because the instance clones it.

```bash
aws cloudformation create-stack --stack-name timeshift --capabilities CAPABILITY_IAM \
  --template-body file://deploy/cfn/timeshift.yaml \
  --parameters ParameterKey=InstanceType,ParameterValue=g6.xlarge \
               ParameterKey=VpcId,ParameterValue=<vpc> ParameterKey=SubnetId,ParameterValue=<subnet> \
               ParameterKey=RepoUrl,ParameterValue=https://github.com/<owner>/timeshift-ai.git
aws cloudformation wait stack-create-complete --stack-name timeshift
aws cloudformation describe-stacks --stack-name timeshift --query "Stacks[0].Outputs"
```

## Step 4: deployment evidence to capture

1. `aws ssm start-session ... AWS-StartPortForwardingSession` → open http://127.0.0.1:8080. The header badge must show `LIVE · cuda`, or `cpu` for the fallback.
2. On the instance: `python scripts/validate_env.py --json /tmp/validate_ec2.json` (Decider memory,
   latency, typed answer; Bedrock via the instance role, which is not root).
3. `python scripts/run_agent.py --scenario solar_cascade --out runs/aws-agent-solar_cascade.jsonl`.
   The event log proves both Bedrock and Decider sit on the execution path.
4. `nvidia-smi` output and `systemctl status decider timeshift`, saved to `docs/deployment/`.
5. Record the demo video from this instance.

## Step 5: teardown (verifiable)

```bash
aws cloudformation delete-stack --stack-name timeshift
aws cloudformation wait stack-delete-complete --stack-name timeshift
python scripts/aws_teardown_check.py --stack timeshift     # read-only; exit 0 = nothing left
```

The check confirms the stack is gone, no tagged instance is in any non-terminated state, and no
project EBS volume, stack security group or stack IAM role remains. Save its output to
`docs/deployment/teardown.txt`.

The root volume has `DeleteOnTermination: true`. The role and instance profile are deleted with the stack.

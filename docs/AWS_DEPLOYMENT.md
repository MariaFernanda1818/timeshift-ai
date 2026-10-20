# AWS deployment

**Status: PLANNED, NOT PROVISIONED.** Nothing in this repository creates AWS resources on its
own. Provisioning requires the owner's explicit approval (cost estimate below).

## Why a GPU instance

Measured on the development laptop (Intel Core i5-1235U, 10 cores, 23.7 GB RAM, CPU only):

- Strands Decider 2B (`strands-decider-2B-qwen3.5-v1-2610`) resident memory: **6.1 GB**.
- `/v1/systemone` latency for a ~1,000–1,340-token TIME//SHIFT gate state: **26–53 s** per request.
- Shorter ~200-token states: ~8.6 s.

That is usable for offline benchmarks but too slow for a live mission-control loop. The
Decider authors report a median of ~115 ms per question on an RTX 3090 for the 2B model.
An NVIDIA L4 (24 GB) is the smallest current-generation AWS GPU that fits it comfortably.

## Architecture (MVP)

```
operator browser --(SSM port-forward, no public port)--> EC2 g6.xlarge (private)
                                                       |-- uvicorn timeshift.server  127.0.0.1:8080
                                                       |-- strands-decider serve     127.0.0.1:8099
                                                       '-- instance role --> Amazon Bedrock (Converse)
CloudWatch agent (optional) <-- journald logs
```

- One instance, two systemd services ([`deploy/ec2/user-data.sh`](../deploy/ec2/user-data.sh)).
- The Decider server is bound to localhost and has no auth. It is never exposed.
- Bedrock access comes from an instance role with a least-privilege policy
  ([`deploy/ec2/iam-policy.json`](../deploy/ec2/iam-policy.json)): it can invoke one model only.
- No inbound security-group rules. Access goes through AWS Systems Manager Session Manager:
  `aws ssm start-session --target i-XXXX --document-name AWS-StartPortForwardingSession --parameters portNumber=8080,localPortNumber=8080`

## Cost estimate (us-east-1, on-demand)

Prices come from third-party listings (Holori/Cloudchipr, updated July 2026). **Verify them on
the AWS pricing page before approval.**

| Item | Rate | Planned usage | Estimate |
|---|---|---|---|
| g6.xlarge (1× L4 24 GB, 4 vCPU, 16 GB) | ~$0.805/h | 30 h (setup, benchmark, demo recording) | ~$24 |
| EBS gp3 100 GB | ~$0.08/GB-month | ~1 week | ~$2 |
| Bedrock Claude Haiku 4.5 | per token | ~2–5 M tokens (agent runs + LLM-judge benchmark) | ~$5–15 (verify current price) |
| Data transfer / CloudWatch | minimal | — | <$2 |
| **Total** | | | **~$33–43** |

Ceiling: stop the instance whenever it is idle. Set an AWS Budget alert at $50.

## Prerequisites to verify first

1. Valid credentials: `aws sts get-caller-identity` (**currently failing on the dev machine: `InvalidClientTokenId`**).
2. Bedrock model access for the chosen model in the region (console → Bedrock → Model access).
3. EC2 quota "Running On-Demand G and VT instances" ≥ 4 vCPUs (new accounts often have 0;
   a quota increase can take hours to days).
4. Then: `python scripts/validate_env.py` on the instance.

## Teardown

```bash
aws ec2 terminate-instances --instance-ids i-XXXX
aws ec2 delete-volume --volume-id vol-XXXX        # if DeleteOnTermination=false
aws iam remove-role-from-instance-profile ... && aws iam delete-role ...
```

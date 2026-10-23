# IAM setup for the TIME//SHIFT deployment (least privilege, no escalation path)

Design:
- The developer identity **never** gets IAM write permissions.
- The CloudFormation stack creates **no IAM resources**. It runs under a pre-created service role
  with EC2-only, tag- and instance-type-scoped permissions.
- The instance uses a pre-created role that can call SSM and invoke one Bedrock model, nothing else.

| File | Attach to | When |
|---|---|---|
| `timeshift-dev-readiness.json` | group `timeshift-developers` (managed policy `timeshift-dev-readiness`) | now |
| `timeshift-instance-role-bedrock.json` | role `timeshift-instance-role` (inline) + AWS managed `AmazonSSMManagedInstanceCore` | before deploy |
| `timeshift-cfn-role-permissions.json` + `timeshift-cfn-role-trust.json` | role `timeshift-cfn-role` | before deploy |
| `timeshift-dev-deploy-temp.json` | group `timeshift-developers` (managed policy `timeshift-dev-deploy-temp`) | only after deployment approval; detach after teardown |

Replace `ACCOUNT_ID` with the 12-digit account ID, `VPC_ID` with the deployment VPC and `SUBNET_ID` with the deployment subnet (reported by
`scripts/aws_readiness.py`). Ready-to-paste copies with the ID substituted are generated outside
the repository so the account ID never enters Git.

Why this removes the escalation path in the earlier draft:
- No `iam:CreateRole`, `iam:PutRolePolicy` or `iam:AttachRolePolicy` for anyone but the admin.
- The developer can pass exactly one role, `timeshift-cfn-role`, only to CloudFormation, and stack
  creation is denied unless that role is used (`cloudformation:RoleArn`).
- The CloudFormation role can pass exactly one role, `timeshift-instance-role`, only to EC2. It can launch
  only m7i-flex.large, c7i.2xlarge or g6.xlarge, and can terminate or delete only resources tagged
  `project=timeshift-hackathon`. Egress rules can only change in the deployment VPC.
- `aws:CalledVia` is no longer relied on.

## Step 1 (now): readiness policy

1. IAM → **Policies** → **Create policy** → **JSON**, then paste
   `C:\timeshift-ai-backup\timeshift-dev-readiness.policy.json`.
2. **Next**: name `timeshift-dev-readiness` → **Create policy**.
3. IAM → **User groups** → `timeshift-developers` → **Permissions** → **Add permissions** →
   **Attach policies** → select `timeshift-dev-readiness` → **Attach policies**.
4. Tell Claude. It then runs `python scripts/aws_readiness.py --profile timeshift-dev`, which validates
   all five policy documents with IAM Access Analyzer and checks quotas, prices, AMIs, VPC and Bedrock.

## Step 2 (before deploy, after Access Analyzer reports no errors)

**Instance role**
1. IAM → **Roles** → **Create role** → *AWS service* → **EC2** → **Next**.
2. Attach **AmazonSSMManagedInstanceCore** → **Next** → name `timeshift-instance-role` → **Create role**.
   The console also creates the matching instance profile.
3. Open the role → **Add permissions** → **Create inline policy** → **JSON**, then paste
   `timeshift-instance-role-bedrock.policy.json` → name `invoke-one-bedrock-model`.

**CloudFormation service role**
1. IAM → **Roles** → **Create role** → **Custom trust policy**, then paste `timeshift-cfn-role-trust.policy.json` → **Next**.
2. Skip managed policies → name `timeshift-cfn-role` → **Create role**.
3. Open it → **Create inline policy** → **JSON**, then paste `timeshift-cfn-role-permissions.policy.json` → name `timeshift-cfn-ec2-scoped`.

## Step 3 (only after the owner approves deployment)
Create the managed policy `timeshift-dev-deploy-temp` from `timeshift-dev-deploy-temp.policy.json` and
attach it to `timeshift-developers`.

## Step 4 (after the teardown check prints CLEAN)
Detach `timeshift-dev-deploy-temp` from the group. When the hackathon is over, delete both roles.

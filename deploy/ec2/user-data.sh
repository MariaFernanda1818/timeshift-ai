#!/bin/bash
# EC2 user-data for TIME//SHIFT on a GPU instance (tested target: g6.xlarge, Deep Learning
# Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04) -- NVIDIA driver preinstalled).
# Runs the Decider server on 127.0.0.1:8099 (never exposed) and the app on 127.0.0.1:8080.
# Access is via SSM port forwarding, not a public port. Bedrock access comes from the
# instance role (no keys on disk).
set -euxo pipefail

REPO_URL="${REPO_URL:-https://github.com/REPLACE_ME/timeshift-ai.git}"
DECIDER_COMMIT="930e6d5de16309be32579f5631a7369a3322140c"
CHECKPOINT="StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"

apt-get update -y
apt-get install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

useradd -m -s /bin/bash timeshift || true
sudo -u timeshift -H bash -c "
  set -euxo pipefail
  cd ~ && git clone $REPO_URL app && cd app
  uv venv .venv --python 3.12
  uv pip install --python .venv/bin/python 'strands-decider[cuda] @ git+https://github.com/strands-labs/strands-decider@$DECIDER_COMMIT'
  uv pip install --python .venv/bin/python -e . -e 'reusable-patterns/counterfactual-decision-gate[strands]'
  cd frontend && npm ci && npm run build
"

cat >/etc/systemd/system/decider.service <<EOF
[Unit]
Description=Strands Decider 2B (private)
After=network-online.target
[Service]
User=timeshift
WorkingDirectory=/home/timeshift/app
ExecStart=/home/timeshift/app/.venv/bin/strands-decider serve $CHECKPOINT --host 127.0.0.1 --port 8099
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/timeshift.service <<EOF
[Unit]
Description=TIME//SHIFT app
After=decider.service
[Service]
User=timeshift
WorkingDirectory=/home/timeshift/app
Environment=AWS_REGION=us-east-1
Environment=BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
Environment=DECIDER_EXPECTED_CHECKPOINT=$CHECKPOINT
ExecStart=/home/timeshift/app/.venv/bin/uvicorn timeshift.server:app --host 127.0.0.1 --port 8080
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now decider.service timeshift.service

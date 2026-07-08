#!/usr/bin/env bash
# One-shot WaitFor (RPC + subscribe) integration test.
# Boots the broker, starts the responder, then runs a config that does RPC -> capture -> subscribe.
# The PayloadStash Expect assertions ARE the test: exit 0 = all passed.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-../.venv/bin/python}"
PS="${PAYLOADSTASH:-../.venv/bin/payloadstash}"
export RMQ_URI="${RMQ_URI:-amqp://guest:guest@localhost:5672/%2F}"

[ -f secrets.env ] || cp secrets.env.example secrets.env

echo "==> Booting RabbitMQ..."
docker compose up -d --wait

echo "==> Starting responder (RPC echo + signal->fanout rebroadcast)..."
"$PY" responder.py &
RESP=$!
trap 'kill "$RESP" 2>/dev/null || true' EXIT
sleep 2

echo "==> Running WaitFor config (RPC -> capture -> subscribe)..."
"$PS" run ./amqp-test-waitfor.yml --out ./out --secrets ./secrets.env --yes

echo
echo "PASS (RPC + WaitFor). Responder stopped; broker still running (docker compose down)."

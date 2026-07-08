#!/usr/bin/env bash
# One-shot AMQP integration test: boot broker -> declare topology -> publish -> verify.
# Leaves the broker running so you can inspect it; run `docker compose down` when done.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-../.venv/bin/python}"
PS="${PAYLOADSTASH:-../.venv/bin/payloadstash}"
export RMQ_URI="${RMQ_URI:-amqp://guest:guest@localhost:5672/%2F}"

[ -f secrets.env ] || cp secrets.env.example secrets.env

echo "==> 1/4 Booting RabbitMQ (docker compose up -d --wait)..."
docker compose up -d --wait

echo "==> 2/4 Declaring exchanges/queues/bindings..."
"$PY" declare.py

echo "==> 3/4 Publishing via PayloadStash..."
"$PS" run ./amqp-test.yml --out ./out --secrets ./secrets.env --yes

echo "==> 4/4 Draining queues and verifying delivery..."
"$PY" drain.py

echo
echo "PASS. Broker still running — inspect at http://localhost:15672 (guest/guest)."
echo "Stop it with:  docker compose down"

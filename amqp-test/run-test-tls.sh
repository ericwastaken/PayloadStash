#!/usr/bin/env bash
# One-shot amqps (TLS) integration test: certs -> TLS broker -> declare -> publish over TLS -> verify.
# Topology declare/drain go over the plaintext listener (5672); the publish goes over amqps (5671).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-../.venv/bin/python}"
PS="${PAYLOADSTASH:-../.venv/bin/payloadstash}"
PLAIN_URI="amqp://guest:guest@localhost:5672/%2F"

[ -f secrets-tls.env ] || cp secrets-tls.env.example secrets-tls.env

echo "==> 1/5 Generating test certs (if missing)..."
[ -f tls/certs/ca.pem ] || ./tls/gen-certs.sh

echo "==> 2/5 Booting TLS RabbitMQ..."
docker compose -f compose.tls.yml up -d --wait

echo "==> 3/5 Declaring topology (over plaintext 5672)..."
RMQ_URI="$PLAIN_URI" "$PY" declare.py

echo "==> 4/5 Publishing over amqps (5671) via PayloadStash..."
"$PS" run ./amqp-test-tls.yml --out ./out --secrets ./secrets-tls.env --yes

echo "==> 5/5 Draining (over plaintext 5672) and verifying..."
RMQ_URI="$PLAIN_URI" "$PY" drain.py

echo
echo "PASS (amqps + CA verification). Stop with:  docker compose -f compose.tls.yml down"

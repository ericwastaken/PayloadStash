#!/usr/bin/env bash
# Generate a throwaway CA + server cert (SAN=localhost) for testing amqps locally.
# NOT for production. Writes tls/certs/{ca.pem, server_certificate.pem, server_key.pem}.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p certs
cd certs

openssl req -x509 -newkey rsa:2048 -nodes -keyout ca_key.pem -out ca.pem \
  -days 3650 -subj "/CN=PayloadStash Test CA" 2>/dev/null

openssl req -newkey rsa:2048 -nodes -keyout server_key.pem -out server.csr \
  -subj "/CN=localhost" 2>/dev/null

openssl x509 -req -in server.csr -CA ca.pem -CAkey ca_key.pem -CAcreateserial \
  -out server_certificate.pem -days 3650 \
  -extfile <(printf "subjectAltName=DNS:localhost,IP:127.0.0.1") 2>/dev/null

rm -f server.csr ca.srl
chmod 644 *.pem   # so the rabbitmq user in the container can read the mounted key (test only)
echo "Wrote tls/certs/{ca.pem, server_certificate.pem, server_key.pem}"

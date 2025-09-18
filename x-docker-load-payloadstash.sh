#!/usr/bin/env bash
set -euo pipefail

# Load the PayloadStash docker image from a local tarball.
# Intended for use on the air-gapped server after extracting payloadstash.zip.
#
# Usage:
#   sudo ./x-docker-load-payloadstash.sh
#   (expects payloadstash.tar in the current directory)

# Require running as root (via sudo)
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Error: this script must be run with sudo (root). Try: sudo $0" >&2
  exit 1
fi

TAR_FILE="payloadstash.tar"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH" >&2
  exit 1
fi

if [[ ! -f "$TAR_FILE" ]]; then
  echo "Error: $TAR_FILE not found in current directory: $(pwd)" >&2
  echo "Make sure you have extracted payloadstash.zip and are running this script inside the payloadstash/ directory." >&2
  exit 1
fi

echo "[load] Loading docker image from $TAR_FILE ..."
docker load -i "$TAR_FILE"
echo "[load] Done. You can now run: ./x-docker-run-payloadstash.sh run config-example.yml"

#!/usr/bin/env bash
set -euo pipefail

# Helper to build the PayloadStash Docker image via compose.
# This script only builds; it does not run the container.
# Usage:
#   ./x-docker-build-payloadstash.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH" >&2
  exit 1
fi

# Prefer docker compose v2 subcommand; fallback to docker-compose if needed
if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "Error: docker compose (v2) or docker-compose (v1) is required" >&2
  exit 1
fi

exec "${DOCKER_COMPOSE[@]}" -f "$PROJECT_ROOT/compose.yml" build payloadstash

#!/usr/bin/env bash
set -euo pipefail

# Helper to run PayloadStash inside Docker with ./config and ./output mounted.
# This script does NOT build the image. Run ./x-docker-build-payloadstash.sh first.
# Usage examples:
#   ./x-docker-run-payloadstash.sh validate my-config.yml
#   ./x-docker-run-payloadstash.sh run my-config.yml
#   ./x-docker-run-payloadstash.sh run nested/other.yml --dry-run --yes
#
# Notes:
# - Config path is assumed to be relative to ./config when not absolute; it will be
#   translated to /app/config/<path> inside the container.
# - Output directory is assumed to be ./output and will be translated to /app/output.
#   If you provide --out or -o, its value will be replaced with /app/output.
# - All other arguments and their order are preserved.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
CONFIG_HOST_DIR="$PROJECT_ROOT/config"
OUTPUT_HOST_DIR="$PROJECT_ROOT/output"

# Ensure expected host directories exist
mkdir -p "$CONFIG_HOST_DIR" "$OUTPUT_HOST_DIR"

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


if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <command> [args...]" >&2
  echo "Commands are the same as the PayloadStash CLI: validate, run" >&2
  exit 2
fi

cmd="$1"; shift || true

# Collect args into an array and rewrite as needed
rewritten=("$cmd")

# Determine if we need to ensure --out for 'run'
ensure_out=false
if [[ "$cmd" == "run" ]]; then
  ensure_out=true
fi

# We expect the first positional arg after the command to be the CONFIG path
config_seen=false

while (( "$#" )); do
  arg="$1"; shift || true

  if [[ "$arg" == "--out" || "$arg" == "-o" ]]; then
    # Replace the provided path (next arg) with /app/output
    rewritten+=("--out")
    if [[ $# -eq 0 ]]; then
      echo "Error: --out provided without a value" >&2
      exit 2
    fi
    _discard="$1"; shift || true
    rewritten+=("/app/output")
    ensure_out=false
    continue
  fi

  if [[ "$arg" == --secrets || "$arg" == --secrets=* ]]; then
    # Ensure the provided secrets file path is rewritten to /app/config
    if [[ "$arg" == --secrets=* ]]; then
      secrets_val="${arg#--secrets=}"
    else
      if [[ $# -eq 0 ]]; then
        echo "Error: --secrets provided without a value" >&2
        exit 2
      fi
      secrets_val="$1"; shift || true
    fi

    # Rewrite secrets_val similar to config handling
    if [[ "$secrets_val" == /* ]]; then
      case "$secrets_val" in
        "$CONFIG_HOST_DIR"/*)
          rel="${secrets_val#"$CONFIG_HOST_DIR"/}"
          rewritten+=("--secrets" "/app/config/$rel")
          ;;
        /app/config/*)
          rewritten+=("--secrets" "$secrets_val")
          ;;
        *)
          echo "Warning: absolute secrets path may not be accessible inside container: $secrets_val" >&2
          rewritten+=("--secrets" "$secrets_val")
          ;;
      esac
    else
      if [[ -f "$CONFIG_HOST_DIR/$secrets_val" ]]; then
        rewritten+=("--secrets" "/app/config/$secrets_val")
      else
        echo "Warning: expected secrets at ./config/$secrets_val not found; passing as-is" >&2
        rewritten+=("--secrets" "$secrets_val")
      fi
    fi
    continue
  fi

  if [[ "$arg" == --* ]]; then
    # Pass through any other flag as-is
    rewritten+=("$arg")
    continue
  fi

  if [[ "$config_seen" == false ]]; then
    # First positional after command: treat as CONFIG path
    cfg="$arg"
    # If absolute path or already /app/config/*, leave as-is but warn that container may not see host path
    if [[ "$cfg" == /* ]]; then
      # Absolute path: try to rewrite if it's under host ./config
      # If the path starts with the host config dir, map the relative remainder
      case "$cfg" in
        "$CONFIG_HOST_DIR"/*)
          rel="${cfg#"$CONFIG_HOST_DIR"/}"
          rewritten+=("/app/config/$rel")
          ;;
        /app/config/*)
          rewritten+=("$cfg")
          ;;
        *)
          echo "Warning: absolute config path may not be accessible inside container: $cfg" >&2
          rewritten+=("$cfg")
          ;;
      esac
    else
      # Relative path: assume it lives under ./config
      if [[ -f "$CONFIG_HOST_DIR/$cfg" ]]; then
        rewritten+=("/app/config/$cfg")
      else
        echo "Warning: expected config at ./config/$cfg not found; passing as-is" >&2
        rewritten+=("$cfg")
      fi
    fi
    config_seen=true
  else
    # Other positional args; just pass through
    rewritten+=("$arg")
  fi

done

# If it's a run and no --out was provided, add it pointing to /app/output
if [[ "$ensure_out" == true ]]; then
  rewritten+=("--out" "/app/output")
fi

# Announce host->container path mappings before container output
echo "[payloadstash-docker] Mounting volumes:" >&2
echo "[payloadstash-docker]   $CONFIG_HOST_DIR -> /app/config" >&2
echo "[payloadstash-docker]   $OUTPUT_HOST_DIR -> /app/output" >&2

# Execute via compose with the mounted volumes
exec "${DOCKER_COMPOSE[@]}" -f "$PROJECT_ROOT/compose.yml" run --rm payloadstash "${rewritten[@]}"

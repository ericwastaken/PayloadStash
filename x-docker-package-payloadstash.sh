#!/usr/bin/env bash
set -euo pipefail

# Package everything needed to run PayloadStash on an air-gapped server.
# - Builds the docker image (payloadstash:local)
# - Saves the image as ./packaged/payloadstash/payloadstash.tar
# - Copies helper scripts, compose.yml, and ./config into the package dir
# - Creates ./packaged/payloadstash.zip with payloadstash/ as the root directory
#
# Usage:
#   ./x-docker-package-payloadstash.sh

# Require running as root (via sudo)
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Error: this script must be run with sudo (root). Try: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PACKAGE_ROOT="$PROJECT_ROOT/packaged"
PAYLOAD_DIR="$PACKAGE_ROOT/payloadstash"
IMAGE_TAG="payloadstash:local"
TAR_NAME="payloadstash.tar"
ZIP_NAME="payloadstash.zip"

# Check required tools
if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH" >&2
  exit 1
fi
if ! command -v zip >/dev/null 2>&1; then
  echo "Error: 'zip' is required to create the package. Please install zip." >&2
  exit 1
fi

# 1) Build the image using the existing helper (preferred) or docker compose
if [[ -x "$PROJECT_ROOT/x-docker-build-payloadstash.sh" ]]; then
  echo "[package] Building image via x-docker-build-payloadstash.sh..."
  "$PROJECT_ROOT/x-docker-build-payloadstash.sh"
else
  echo "[package] Helper build script not found; building via docker compose..."
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$PROJECT_ROOT/compose.yml" build payloadstash
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "$PROJECT_ROOT/compose.yml" build payloadstash
  else
    echo "Error: docker compose (v2) or docker-compose (v1) is required to build" >&2
    exit 1
  fi
fi

# 2) Prepare package directories
mkdir -p "$PAYLOAD_DIR"

# 3) Save the image to a tarball
echo "[package] Saving image $IMAGE_TAG to $PAYLOAD_DIR/$TAR_NAME ..."
# docker save requires root; this script enforces sudo above
docker image save -o "$PAYLOAD_DIR/$TAR_NAME" "$IMAGE_TAG"

# 4) Copy required files into the package directory
echo "[package] Copying helper scripts, compose.yml, and config/ ..."
cp -f "$PROJECT_ROOT/x-docker-run-payloadstash.sh" "$PAYLOAD_DIR/"
cp -f "$PROJECT_ROOT/x-docker-load-payloadstash.sh" "$PAYLOAD_DIR/" || true
cp -f "$PROJECT_ROOT/compose.yml" "$PAYLOAD_DIR/"
# Copy config directory entirely
rsync -a --delete "$PROJECT_ROOT/config/" "$PAYLOAD_DIR/config/" 2>/dev/null || {
  # Fallback to cp -a if rsync isn't available
  mkdir -p "$PAYLOAD_DIR/config"
  cp -a "$PROJECT_ROOT/config/." "$PAYLOAD_DIR/config/"
}

# 5) Create the zip with payloadstash/ as root inside the archive
echo "[package] Creating zip $PACKAGE_ROOT/$ZIP_NAME ..."
rm -f "$PACKAGE_ROOT/$ZIP_NAME"
(
  cd "$PACKAGE_ROOT" && zip -r "$ZIP_NAME" "$(basename "$PAYLOAD_DIR")"
)

echo "[package] Done. Package created at: $PACKAGE_ROOT/$ZIP_NAME"

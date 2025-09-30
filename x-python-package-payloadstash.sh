#!/usr/bin/env bash
set -euo pipefail

# Package a native Python distribution of PayloadStash for transfer to another machine
# where the recipient will run `python3 setup.py install` (or `pip install .`).
#
# What this script does:
# - Creates ./packaged-python/payloadstash-python/
# - Copies setup.py, requirements.txt, payload_stash/ package, LICENSE, README.md
# - Copies ./config/ README and example files
# - Produces ./packaged-python/payloadstash-python.zip with payloadstash-python/ as the root
#
# Usage:
#   ./x-python-package-payloadstash.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PACKAGE_ROOT="$PROJECT_ROOT/packaged-python"
PAYLOAD_DIR="$PACKAGE_ROOT/payloadstash-python"
ZIP_NAME="payloadstash-python.zip"

# Determine target ownership (prefer invoking user when run via sudo)
OWNER_UID="${SUDO_UID:-$(id -u)}"
OWNER_GID="${SUDO_GID:-$(id -g)}"

# Check required tools
if ! command -v zip >/dev/null 2>&1; then
  echo "Error: 'zip' is required to create the package. Please install zip." >&2
  exit 1
fi

# Python is not strictly required on the packaging machine, but we try to provide a nicer message.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Warning: python3 not found on this machine. That's OK for packaging, but the target will need Python >= 3.8." >&2
fi

# 1) Prepare package directories - clear previous output
rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR"

# 2) Copy Python project files
cp -f "$PROJECT_ROOT/setup.py" "$PAYLOAD_DIR/"
cp -f "$PROJECT_ROOT/requirements.txt" "$PAYLOAD_DIR/" || true
cp -f "$PROJECT_ROOT/LICENSE" "$PAYLOAD_DIR/" || true
cp -f "$PROJECT_ROOT/README.md" "$PAYLOAD_DIR/" || true

# Copy the package source tree
mkdir -p "$PAYLOAD_DIR/payload_stash"
# Use rsync if available to preserve structure; fallback to cp -a
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
    "$PROJECT_ROOT/payload_stash/" "$PAYLOAD_DIR/payload_stash/"
else
  cp -a "$PROJECT_ROOT/payload_stash/." "$PAYLOAD_DIR/payload_stash/"
  # Remove common Python cache files if any were copied
  find "$PAYLOAD_DIR/payload_stash" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  find "$PAYLOAD_DIR/payload_stash" -name '*.py[co]' -type f -delete 2>/dev/null || true
fi

# 3) Include config samples and README
mkdir -p "$PAYLOAD_DIR/config"
if [[ -f "$PROJECT_ROOT/config/README.md" ]]; then
  cp -f "$PROJECT_ROOT/config/README.md" "$PAYLOAD_DIR/config/README.md"
fi
if [[ -f "$PROJECT_ROOT/config/config-example.yml" ]]; then
  cp -f "$PROJECT_ROOT/config/config-example.yml" "$PAYLOAD_DIR/config/config-example.yml"
fi
if [[ -f "$PROJECT_ROOT/config/secrets-example.env" ]]; then
  cp -f "$PROJECT_ROOT/config/secrets-example.env" "$PAYLOAD_DIR/config/secrets-example.env"
fi

# Ensure payload directory is owned by the invoking user
if command -v chown >/dev/null 2>&1; then
  chown -R "${OWNER_UID}:${OWNER_GID}" "$PAYLOAD_DIR" || true
fi

# 4) Create or update top-level README for packaged-python (instructions live one directory up as well)
mkdir -p "$PACKAGE_ROOT"

# 5) Create the zip with payloadstash-python/ as root inside the archive
echo "[package-python] Creating zip $PACKAGE_ROOT/$ZIP_NAME ..."
rm -f "$PACKAGE_ROOT/$ZIP_NAME"
(
  cd "$PACKAGE_ROOT" && zip -r "$ZIP_NAME" "$(basename "$PAYLOAD_DIR")"
)

# Ensure the zip file is owned by the invoking user
if command -v chown >/dev/null 2>&1; then
  chown "${OWNER_UID}:${OWNER_GID}" "$PACKAGE_ROOT/$ZIP_NAME" || true
fi

echo "[package-python] Done. Package created at: $PACKAGE_ROOT/$ZIP_NAME"

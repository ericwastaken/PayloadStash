#!/usr/bin/env bash
set -euo pipefail

# Update PayloadStash package metadata versions in the known project files.
# Usage:
#   ./x-payloadstash-version-set.sh 1.0.6

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

usage() {
  echo "Usage: $(basename "$0") MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]" >&2
}

if [[ "$#" -ne 1 ]]; then
  usage
  exit 1
fi

NEW_VERSION="$1"
SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z][0-9A-Za-z.-]*)?(\+[0-9A-Za-z][0-9A-Za-z.-]*)?$'

if [[ ! "$NEW_VERSION" =~ $SEMVER_RE ]]; then
  echo "Error: version must be semantic version format, such as 1.0.6 or 1.0.6-rc.1+build.1" >&2
  exit 1
fi

UPDATED_FILES=()

update_required() {
  local rel_path="$1"
  local pattern="$2"
  local replacement="$3"
  local file="$PROJECT_ROOT/$rel_path"

  if [[ ! -f "$file" ]]; then
    echo "Error: required metadata file missing: $rel_path" >&2
    exit 1
  fi

  if ! perl -0pi -e "$pattern" "$file"; then
    echo "Error: failed updating $rel_path" >&2
    exit 1
  fi

  if ! grep -Eq "$replacement" "$file"; then
    echo "Error: expected version declaration was not updated in $rel_path" >&2
    exit 1
  fi

  UPDATED_FILES+=("$rel_path")
}

update_optional() {
  local rel_path="$1"
  local pattern="$2"
  local replacement="$3"
  local file="$PROJECT_ROOT/$rel_path"

  if [[ ! -f "$file" ]]; then
    return
  fi

  if ! perl -0pi -e "$pattern" "$file"; then
    echo "Error: failed updating $rel_path" >&2
    exit 1
  fi

  if ! grep -Eq "$replacement" "$file"; then
    echo "Error: expected version declaration was not updated in $rel_path" >&2
    exit 1
  fi

  UPDATED_FILES+=("$rel_path")
}

SETUP_PATTERN='s/(\bversion=")[^"]+(")/${1}'"$NEW_VERSION"'${2}/ or die "version pattern not found\n"'
INIT_PATTERN='s/(__version__\s*=\s*")[^"]+(")/${1}'"$NEW_VERSION"'${2}/ or die "__version__ pattern not found\n"'
PYPROJECT_PATTERN='s/(\[project\].*?\nversion\s*=\s*")[^"]+(")/${1}'"$NEW_VERSION"'${2}/s or die "project version pattern not found\n"'

update_required "setup.py" "$SETUP_PATTERN" '^    version="'"$NEW_VERSION"'",$'
update_required "payload_stash/__init__.py" "$INIT_PATTERN" '^__version__ = "'"$NEW_VERSION"'"$'
update_required "pyproject.toml" "$PYPROJECT_PATTERN" '^version = "'"$NEW_VERSION"'"$'

update_optional "packaged-python/payloadstash-python/setup.py" "$SETUP_PATTERN" '^    version="'"$NEW_VERSION"'",$'
update_optional "packaged-python/payloadstash-python/payload_stash/__init__.py" "$INIT_PATTERN" '^__version__ = "'"$NEW_VERSION"'"$'
update_optional "packaged-python/payloadstash-python/pyproject.toml" "$PYPROJECT_PATTERN" '^version = "'"$NEW_VERSION"'"$'

echo "Updated PayloadStash package metadata version to $NEW_VERSION:"
for rel_path in "${UPDATED_FILES[@]}"; do
  echo "- $rel_path"
done
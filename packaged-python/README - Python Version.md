# PayloadStash packaged Python distribution

This directory is maintained for people who produce PayloadStash release artifacts. Operational installation and usage instructions belong in the [PayloadStash user guide](https://ericwastaken.github.io/PayloadStash/install/).

## Build the artifact

From the repository root:

```bash
./x-python-package-payloadstash.sh
```

The script stages `packaged-python/payloadstash-python/` and creates `packaged-python/payloadstash-python.zip`.

## Archive contents

The archive contains the package source, `pyproject.toml`, `setup.py`, runtime requirements, license, repository overview, and configuration examples. It is intended for transfer to hosts where a source bundle is required.

## Maintainer checks

- Set the intended version before packaging.
- Build from a clean, reviewed source revision.
- Inspect the archive list and confirm no local secrets or generated output are included.
- Extract into a temporary directory and verify its metadata and `config/` samples.
- Follow the user guide when smoke-testing artifact consumption; do not duplicate those instructions here.

The Git-based UV tool installation documented for users is separate from this ZIP artifact and does not imply a PyPI publication.
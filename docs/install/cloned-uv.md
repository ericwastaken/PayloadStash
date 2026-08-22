# Run a cloned repository with UV

Use this path when you want to run the checked-out source without manually creating or activating a virtual environment.

## Prerequisites

- Git
- [UV](https://docs.astral.sh/uv/getting-started/installation/)

## Install and verify

```bash
git clone https://github.com/ericwastaken/PayloadStash.git
cd PayloadStash
uv sync
uv run payloadstash --help
```

`uv sync` creates or updates the environment from `pyproject.toml` and `uv.lock`. Run every PayloadStash command through `uv run`:

```bash
uv run payloadstash validate ./config/config-example.yml
uv run payloadstash validate ./config/config-example.yml --writeResolved
uv run payloadstash run ./config/config-example.yml --out ./output --yes
```

## Update or remove

```bash
git pull --ff-only
uv sync
```

To remove the installation, delete the checkout. UV's project environment is stored in the checkout's `.venv` directory.
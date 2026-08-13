# PayloadStash - Packaged Python Distribution

This directory holds the packaged Python distribution produced by the helper script. The primary deliverable is a single
zip archive you can move to another machine and install into its local Python environment.

To create a new release, run the packaging script from the root of the repository:

```bash
./x-python-package-payloadstash.sh
```

## What is `payloadstash-python.zip`?
`payloadstash-python.zip` is a bundle that includes:
- `pyproject.toml` — UV-native project metadata and console script declaration.
- `setup.py` — the installer entry point for the setup.py/manual path.
- `requirements.txt` — Python dependencies for the project.
- `payload_stash/` — the Python package source code.
- `LICENSE`, `README.md` — project docs.
- `config/` — a folder with `config-example.yml` and `secrets-example.env` you can copy and customize.

After extracting, you will have a folder named `payloadstash-python/` with these items.

## Move the zip to another server
You can transfer the archive using any method you prefer:
- scp: `scp packaged-python/payloadstash-python.zip user@server:/tmp/`
- rsync: `rsync -avh packaged-python/payloadstash-python.zip user@server:/tmp/`
- Removable media: copy `payloadstash-python.zip` to a USB drive and then to the server

On the target machine, place `payloadstash-python.zip` in a working directory, e.g. `/opt/` or your home directory.

## Extract the archive
From the directory where `payloadstash-python.zip` is located, run:

- With unzip installed: `unzip payloadstash-python.zip` (or `7z x payloadstash-python.zip`)

This will create a folder named `payloadstash-python/`. Change into that directory:

`cd payloadstash-python`

## Prerequisites on the target machine
- Python 3.8 or newer
- Internet access to download and install Python packages from PyPI (for requirements)
- A C/C++ build toolchain may be necessary if any dependencies require compilation on your platform

Check your Python version with:
- `python3 --version`

## Install PayloadStash into the environment
Choose one native Python path.

### Option A: UV (recommended)

- Sync dependencies: `uv sync`
- Check the CLI: `uv run payloadstash --help`
- Run a config: `uv run payloadstash run ./config/config-example.yml --out ./output`

### Option B: setup.py/manual path

- Using setup.py directly: `python3 setup.py install`
- Or manually create a venv and install with pip:
  `python3 -m venv .venv && .venv/bin/python -m pip install -U pip && .venv/bin/pip install .`

This project’s `setup.py` includes a custom step that attempts to create a `.venv` virtual environment at the project root
and install requirements there. If that step fails, the installation will still proceed, but you may want to manually
create and use a virtual environment for isolation.

## Configure PayloadStash

For the full documentation on configuring PayloadStash, see the [PayloadStash on GitHub](https://github.com/ericwastaken/PayloadStash).

- Copy the example config to a new file under `./config/` and edit it to your needs:
  - `cp config/config-example.yml config/my-config.yml`
  - Edit `config/my-config.yml`
- Secrets/Environment variables: if your configuration expects a `.env`/env file, place it in the `config/` folder.

## Run the CLI
If you chose UV, run commands through `uv run payloadstash ...`. If you chose the setup.py/manual path, the
`payloadstash` command should be available in your environment. Examples:
- Validate a config: `uv run payloadstash validate ./config/config-example.yml` or `payloadstash validate ./config/config-example.yml`
- Execute a run: `uv run payloadstash run ./config/config-example.yml` or `payloadstash run ./config/config-example.yml`
- With secrets: `uv run payloadstash run ./config/config-example.yml --secrets ./config/secrets.env` or `payloadstash run ./config/config-example.yml --secrets ./config/secrets.env`

If you installed into a virtual environment manually, ensure it is activated before running the command.

## Troubleshooting
- If pip installation of dependencies fails due to networking, ensure the machine has internet access or use a suitable
  package mirror/repository accessible from the environment.
- If the `payloadstash` command is not found after installation, ensure your Python environment’s scripts/bin directory
  is in PATH, or call it via `python -m payload_stash.main`.

## Where did this come from?
This `packaged-python/` directory is produced by the repository’s packaging script and may be excluded from source control.

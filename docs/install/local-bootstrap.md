# Local bootstrap installation

Use the bootstrap-managed installation when you want a repository checkout with its own `.venv` and the convenient `./payloadstash` wrapper. The bootstrap avoids system-Python restrictions such as PEP 668.

## Prerequisites

- Git
- Python 3.8 or newer
- Internet access while Python dependencies are installed

## Install

```bash
git clone https://github.com/ericwastaken/PayloadStash.git
cd PayloadStash
python3 bootstrap.py
./payloadstash --help
```

The script creates `.venv` beside `bootstrap.py`, upgrades its packaging tools, and installs PayloadStash into it. It does not require activating the environment.

You can also install and immediately run a command:

```bash
python3 bootstrap.py -- run payloadstash --help
```

## Update or reinstall

```bash
git pull --ff-only
python3 bootstrap.py --reinstall
```

Use `python3 bootstrap.py --editable` only when you intend to modify the source. To remove this installation, delete the cloned directory; the virtual environment is contained within it.

## Run commands

Paths are relative to the repository directory unless you use absolute paths:

```bash
./payloadstash validate ./config/config-example.yml
./payloadstash validate ./config/config-example.yml --writeResolved
./payloadstash run ./config/config-example.yml --out ./output --yes
```

!!! note
    The live CLI has no separate `resolve` command. Use `validate --writeResolved` to write a resolved file beside the source configuration, or `run` to write one in the timestamped run directory.
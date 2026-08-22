# Install a GitHub Release

Use a GitHub Release when you want a stable, published PayloadStash version without installing Git. This is the simplest native installation for most users.

[Download the latest release](https://github.com/ericwastaken/PayloadStash/releases/latest){ .md-button .md-button--primary }

## Prerequisites

- Python 3.8 or newer
- A tool that can extract ZIP archives
- Internet access while Python dependencies are installed

## Download and install

1. Open the [latest PayloadStash release](https://github.com/ericwastaken/PayloadStash/releases/latest).
2. Expand **Assets** and download **Source code (zip)**.
3. Extract the archive into the directory where you want to keep PayloadStash.
4. Open a terminal in the extracted directory and run:

```bash
python3 bootstrap.py
./payloadstash --help
```

GitHub names the extracted directory for the selected version, such as `PayloadStash-1.2.0`. The bootstrap creates a private `.venv` inside that directory and installs the `./payloadstash` wrapper; you do not need to activate the environment.

!!! note "Release archive contents"
    GitHub provides the source ZIP for every published release, even when the release has no additional packaged assets. This installation uses that versioned archive; it does not install from PyPI or track the changing `main` branch.

## Update or remove

To update, download the newer release archive, extract it into a new directory, and run `python3 bootstrap.py` there. Keep your configuration and output outside the old extracted directory, or copy them elsewhere before deleting it.

To remove PayloadStash, delete its extracted directory. The bootstrap-managed virtual environment is contained inside it.

## Run commands

Run commands from the extracted directory, or use absolute paths for configuration and output locations:

```bash
./payloadstash validate ./config/config-example.yml
./payloadstash validate ./config/config-example.yml --writeResolved
./payloadstash run ./config/config-example.yml --out ./output --yes
```

Continue with [Create your first configuration](../getting-started/first-config.md) when you are ready to use your own targets.
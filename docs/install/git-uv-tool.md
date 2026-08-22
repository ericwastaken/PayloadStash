# Install from GitHub with UV

Use a Git-based UV tool installation when you want a native `payloadstash` command without maintaining a source checkout. This installs directly from GitHub; it does not use PyPI.

## Prerequisites

- Git
- [UV](https://docs.astral.sh/uv/getting-started/installation/)

## Install

```bash
uv tool install git+https://github.com/ericwastaken/PayloadStash.git
payloadstash --help
```

If UV reports that its tool directory is not on `PATH`, run `uv tool update-shell`, start a new shell, and try again.

Pin a release tag when you need reproducible behavior:

```bash
uv tool install 'git+https://github.com/ericwastaken/PayloadStash.git@v1.2.0'
```

## Update or remove

Reinstall from GitHub to move to the current branch head:

```bash
uv tool install --force git+https://github.com/ericwastaken/PayloadStash.git
```

Remove the managed tool with:

```bash
uv tool uninstall payloadstash
```

## Run commands

The CLI receives normal host paths:

```bash
payloadstash validate ./config.yml
payloadstash validate ./config.yml --writeResolved
payloadstash run ./config.yml --out ./output --yes
```
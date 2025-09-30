# PayloadStash - Packaged Distribution

This directory holds the packaged distribution artifacts produced by the packaging script. The primary deliverable is a 
single zip archive you can move to another (possibly air‑gapped) Linux server and run without building anything there.

To create a new release, run the packaging script from the root of the repository:

```bash
./x-docker-package-payloadstash.sh
```

## What is `payloadstash.zip`?
`payloadstash.zip` is a self-contained bundle that includes:
- `payloadstash.tar` — a Docker image tarball for the PayloadStash application.
- `x-docker-load-payloadstash.sh` — helper script to load the Docker image from the tarball on the target server.
- `x-docker-run-payloadstash.sh` — helper script to run PayloadStash via Docker Compose.
- `compose.yml` — a compose file used by the run script.
- `config/` — a config folder with `config-example.yml` you can copy and customize.
- `output/` — will be created on first run to store run results.

After extracting, you will have a `payloadstash/` folder containing these items.

## Move the zip to another (Linux) server
You can transfer the archive using any method you prefer. Examples:
- scp: `scp packaged/payloadstash.zip user@server:/tmp/`
- rsync: `rsync -avh packaged/payloadstash.zip user@server:/tmp/`
- Removable media: copy `payloadstash.zip` to a USB drive and then to the server

> **Note:** You only need to transfer the zip file and the README.md. Everything else is already included in the zip.

On the target server, place `payloadstash.zip` in a working directory, e.g. `/opt/` or your home directory.

## Extract the archive (Linux)
From the directory where `payloadstash.zip` is located, run:

- With unzip installed: `unzip payloadstash.zip` or `7z x payloadstash.zip`

This will create a folder named `payloadstash/` with the contents described above. Change into that directory:

`cd payloadstash`

If needed, make the helper scripts executable:

`chmod +x *.sh`

## Prerequisites on the target server
- Docker Engine installed and running
- Docker Compose (docker compose v2 preferred; docker-compose v1 also supported)
- Sudo privileges to load images (docker load requires root) and to run the helper scripts (the run script fixes output permissions)

You can check availability with:
- `docker --version`
- `docker compose version` (or `docker-compose --version`)

## Load the Docker image from the tarball
Run the provided load script from inside the `payloadstash/` directory:

`sudo ./x-docker-load-payloadstash.sh`

What this does:
- Verifies Docker is available
- Loads `payloadstash.tar` into the local Docker image cache

On success, you will see a message indicating the image was loaded. The image tag used by the compose file is `payloadstash:local`.

## Configure PayloadStash

For the full documentation on configuring PayloadStash, see the [PayloadStash on GitHub](https://github.com/ericwastaken/PayloadStash).

- Copy the example config to a new file under `./config/` and edit it to your needs:
  - `cp config/config-example.yml config/my-config.yml`
  - Edit `config/my-config.yml` with your settings.
- Secrets/Environment variables: if your configuration expects a `.env`/env file, place it in the `config/` folder and 
  reference it from your command line.

## Run PayloadStash with the run script
From inside the `payloadstash/` directory, you can invoke the CLI through Docker using the helper script. 
All files (config, secrets, etc.) must be located in the `./config` directory!

Common examples:

- Validate a config:
  - `sudo ./x-docker-run-payloadstash.sh validate config-example.yml`
  - or `sudo ./x-docker-run-payloadstash.sh validate my-config.yml`

- Execute a run using a config:
  - `sudo ./x-docker-run-payloadstash.sh run config-example.yml`
  - or `sudo ./x-docker-run-payloadstash.sh run my-config.yml`

- Execute a run using a config and a secrets file:
    - `sudo ./x-docker-run-payloadstash.sh run config-example.yml --secrets secrets.env`
    - or `sudo ./x-docker-run-payloadstash.sh run my-config.yml --secrets secrets.env`


Notes:
- You must run the helper scripts with sudo. This is required so the run script can correct ownership of files written to ./output.
- After the container completes, the run script will chown -R ./output back to the invoking non-root user (the sudo user).
- The script mounts `./config` to `/app/config` and `./output` to `/app/output` in the container.
- If you do not pass an `--out` flag, the script automatically sets `--out /app/output` so results appear under `./output` on the host.
- If you pass a `--secrets` flag, the script automatically sets `--secrets /app/config/secrets.env` so the secrets file 
  appears in the container. This means you should place the secrets file in the config directory.
- You may pass additional CLI flags after the config file; they will be forwarded to the application. For example:
  - --yes - which will bypass the command line prompt for confirmation

## Troubleshooting
- If you see `Error: docker is not installed or not in PATH` — install Docker and ensure your user has permission to run it.
- If `docker compose` is not available, install Docker Compose v2 or use `docker-compose` v1.
- Ensure you run the scripts from inside the extracted `payloadstash/` directory where `payloadstash.tar` resides.

## Where did this come from?
This `packaged/` directory is produced by the repository build/packaging process and is excluded from source control. 
The `payloadstash.zip` inside it is the artifact intended for distribution to target environments.
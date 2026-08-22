# Run the GHCR image

Use the public GitHub Container Registry image when you want PayloadStash isolated from the host's Python environment.

## Prerequisites

- Docker Engine or Docker Desktop
- An `amd64`-compatible Docker runtime, or emulation for `linux/amd64`

The current repository container flow explicitly targets `linux/amd64`. On Apple Silicon or other architectures, Docker may use emulation and run more slowly.

## Run from your working directory

The following command mounts the current host directory at `/working`, uses that as the container working directory, and leaves output on the host:

```bash
docker run --rm --platform linux/amd64 \
  -v "$(pwd):/working" -w /working \
  ghcr.io/ericwastaken/payloadstash:main \
  run ./config/config-example.yml --out ./output --yes
```

Validate the same configuration without making requests:

```bash
docker run --rm --platform linux/amd64 \
  -v "$(pwd):/working" -w /working \
  ghcr.io/ericwastaken/payloadstash:main \
  validate ./config/config-example.yml
```

All paths passed to PayloadStash must be visible inside the container. With this mount style, host paths below the current directory map directly below `/working`.

## Use secrets

Keep the secrets file inside the mounted working directory and pass its container-visible relative path:

```bash
docker run --rm --platform linux/amd64 \
  -v "$(pwd):/working" -w /working \
  ghcr.io/ericwastaken/payloadstash:main \
  run ./config/config.yml --out ./output --yes \
  --secrets ./config/secrets.env
```

## Choose and update the image tag

- `:main` follows successful image publications from the default branch.
- A version tag such as `:1.2.0` keeps runs on a specific release.

Refresh the moving tag with:

```bash
docker pull --platform linux/amd64 ghcr.io/ericwastaken/payloadstash:main
```

Remove it with `docker image rm ghcr.io/ericwastaken/payloadstash:main`.

!!! note "Different paths in packaged Docker helpers"
    The repository's packaged Docker helper uses `./config` → `/app/config` and `./output` → `/app/output`. Those `/app` paths apply to that helper and Compose flow; the direct GHCR commands above deliberately use `/working` instead.
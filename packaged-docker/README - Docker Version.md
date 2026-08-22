# PayloadStash packaged Docker distribution

This directory is maintained for people who produce the air-gapped PayloadStash container bundle. Users running the published GHCR image should follow the [GHCR Docker guide](https://ericwastaken.github.io/PayloadStash/install/docker/).

## Build the artifact

From the repository root:

```bash
./x-docker-package-payloadstash.sh
```

The script creates `packaged-docker/payloadstash.zip`, containing the exported image tarball, Compose file, load/run helpers, license, repository overview, and configuration samples.

## Maintainer context

- The packaged Compose flow uses the local image tag `payloadstash:local`.
- Its helper mounts `./config` at `/app/config` and `./output` at `/app/output`.
- The current Compose/build path targets `linux/amd64`; preserve or deliberately revise that compatibility contract when changing packaging.
- Loading and running an air-gapped bundle is a different consumption path from pulling `ghcr.io/ericwastaken/payloadstash`.

## Maintainer checks

- Build from a clean, reviewed source revision with the intended version.
- Inspect the ZIP and image metadata; ensure no secrets or generated run output are present.
- Extract and load the bundle in a disposable Linux environment.
- Verify the included helper scripts and configuration sample against the packaged image.
- Keep artifact-production details here and update user-facing consumption guidance only in `docs/`.
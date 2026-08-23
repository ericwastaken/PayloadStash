# PayloadStash development and release guide

This guide covers maintainer development checks, GitHub Release publication, and GHCR container maintenance. End-user installation and operation remain documented in the [PayloadStash user guide](https://ericwastaken.github.io/PayloadStash/).

## Release publication model

The workflow in `.github/workflows/docker-publish.yml` runs only when a GitHub Release is published:

```yaml
on:
  release:
    types:
      - published
```

- A normal commit or merge to `main` does not build or publish a GHCR image.
- Saving a draft release does not trigger publication.
- Publishing a stable release or prerelease triggers the workflow once for that release tag.
- The released commit must already be contained in `main`.
- The workflow publishes only `linux/amd64` images.

## Prepare a release

Start from an updated `main` checkout and confirm that the working tree contains only the intended release work:

```bash
git switch main
git pull --ff-only
git status --short --branch
```

Choose a semantic version and update every maintained version declaration with the repository helper. Pass the version without the Git tag's `v` prefix:

```bash
./x-payloadstash-version-set.sh 1.3.0
```

The helper updates `setup.py`, `pyproject.toml`, `payload_stash/__init__.py`, and the corresponding packaged Python sources when present. Review all changes:

```bash
git diff
```

Run the application tests before committing:

```bash
/opt/homebrew/bin/uv run python tests/test_asserts.py
/opt/homebrew/bin/uv run python tests/test_header_case.py
/opt/homebrew/bin/uv run python tests/test_url_operators.py
/opt/homebrew/bin/uv run python tests/test_amqp.py
```

When documentation changed, also run:

```bash
.venv-docs/bin/mkdocs build --strict
```

Commit the version bump, release notes, and intended release changes, then push them to `main`. Do not create the release tag before the version bump is on `main`.

## Publish through the GitHub UI

1. Open the repository's **Releases** page and select **Draft a new release**.
2. Create a tag named `vMAJOR.MINOR.PATCH`, such as `v1.3.0`.
3. Target the exact `main` commit containing the matching version bump.
4. Add the release title and notes.
5. Select **Set as a pre-release** only for versions such as `v1.4.0-rc.1`.
6. Select **Publish release**.

The tag must include the `v` prefix, while the version stored in project files must not. For example, tag `v1.3.0` must match project version `1.3.0`.

## Automated release gates

Before GHCR authentication or publication, the workflow:

1. Validates the release tag as SemVer beginning with `v`.
2. Compares the tag with `pyproject.toml` and `payload_stash/__init__.py`.
3. Confirms that the tagged commit is contained in `origin/main`.
4. Installs the project and runs all four test scripts.
5. Builds a `linux/amd64` release candidate.
6. Verifies the version and CLI entry point inside the candidate image.
7. Authenticates to GHCR and publishes the validated image.

Stable release `v1.3.0` produces these image tags:

```text
1.3.0
1.3
latest
```

Prerelease `v1.4.0-rc.1` produces only:

```text
1.4.0-rc.1
```

Prereleases do not move `latest`. The workflow does not create `main` or `sha-*` tags.

## Verify a published release

Review the workflow run under the repository's **Actions** tab and inspect the [PayloadStash GHCR package](https://github.com/ericwastaken/PayloadStash/pkgs/container/payloadstash). Then verify the exact image:

```bash
docker buildx imagetools inspect ghcr.io/ericwastaken/payloadstash:1.3.0
docker pull --platform linux/amd64 ghcr.io/ericwastaken/payloadstash:1.3.0
docker run --rm --platform linux/amd64 \
    ghcr.io/ericwastaken/payloadstash:1.3.0 --version
```

For a stable release, verify that `latest` resolves to the same image digest.

## Multiple GitHub identities

Git remotes may use a local SSH alias, but GitHub CLI API authentication still uses `github.com`. Before any release or package mutation, verify both the API identity and repository remote:

```bash
gh auth switch --hostname github.com --user ericwastaken
gh api --hostname github.com user --jq .login
git remote get-url origin
```

The API command must report `ericwastaken`. An SSH remote such as `git@github-eric.com:ericwastaken/PayloadStash.git` may remain unchanged because the alias selects the appropriate SSH identity.

Package cleanup additionally requires `read:packages` and `delete:packages` scopes. Inspect them with `gh auth status --active --hostname github.com`; never display the token.

## Failure and recovery

- For a transient GitHub, runner, or registry failure, rerun the failed workflow from the Actions page.
- A rerun always uses the same release tag and commit. It cannot incorporate later fixes pushed to `main`.
- If the tag points at the wrong commit or the version metadata is wrong, stop. If nothing was published, correct the release and tag only with explicit maintainer approval. If an image was published, prefer a new patch release rather than moving a published tag.
- Do not delete or retag release images merely to make a failed workflow green.

## GHCR maintenance

Deleting package versions is a separate maintenance action and is never part of routine release publication. It requires explicit maintainer authorization.

Buildx publications can appear in GitHub Packages as a tagged image index plus untagged platform and provenance child records. Before deleting untagged records, resolve the manifests referenced by every release image and preserve those child digests:

```bash
docker buildx imagetools inspect \
    ghcr.io/ericwastaken/payloadstash:1.3.0 --raw
```

Do not delete a package version merely because it carries a `sha-*` tag when the same version also carries a semantic release tag. Deleting the version would remove all tags attached to that release digest.

## Agent authorization boundary

An agent may inspect release readiness, update local version files, run tests, and prepare release notes when asked. Creating or publishing a GitHub Release, moving or deleting a tag, publishing an image, or deleting GHCR package versions changes external state and requires explicit user authorization for that action.

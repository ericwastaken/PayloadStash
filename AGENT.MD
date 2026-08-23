# Documentation ownership

PayloadStash separates end-user documentation from repository-facing developer and maintainer documentation.

## Source-of-truth matrix

| Change | Required documentation |
| --- | --- |
| Installation, CLI, configuration, runtime behavior, outputs, examples, or troubleshooting visible to users | Update the applicable Markdown under `docs/`; do not recreate detailed user guides in root or packaged READMEs |
| Developer setup, architecture, tests, or contribution workflow | Update the relevant repository Markdown only |
| GitHub Release, GHCR publication, release recovery, or registry maintenance | Update `DEVELOPMENT.md`, the applicable workflow, and concise links or summaries in `README.md`; update packaged READMEs only when their artifact-production process changes |
| Change affecting both audiences | Update each source for its audience, keep terminology and links aligned, and avoid copying the same guide into both |
| Configuration/model change | Update `docs/reference/configuration.md`, affected `docs/configuration/` topics, and `config/config-example.yml` when an executable example should change; update developer docs only for implementation/maintenance impact |
| CLI change | Update `docs/reference/cli.md`, affected workflows/examples, and repository developer notes only if development commands change |
| Behavior used by agents to author or run configurations | Update `SKILL.md` alongside the applicable user guide and executable examples; keep its front matter, field rules, command forms, and complete examples current |
| Agent-skill installation or discovery change | Update `docs/agent-skill.md`, its home-page/navigation links, and the install location or download URL shown there |
| Distribution change | Put artifact-production details in the relevant packaged README and artifact-consumption instructions in `docs/install/` |
| Branding or navigation change | Update `mkdocs.yml`, `docs/assets/` or site styling, and repository links where applicable |

## Boundaries

- `docs/` is the sole source of truth for end-user installation and operation.
- `README.md` is a concise project/developer entry point and links users to GitHub Pages.
- `DEVELOPMENT.md` is the source of truth for maintainer release preparation, GitHub Release publication, automated GHCR behavior, verification, and package cleanup safety.
- `packaged-python/README - Python Version.md` and `packaged-docker/README - Docker Version.md` describe producing and maintaining artifacts, not using PayloadStash.
- `config/config-example.yml` remains the canonical executable sample; `config/README.md` explains sample-file maintenance.
- `SKILL.md` is the installable agent instruction source. It complements the end-user site and must reflect current schema, operator, transport, CLI, and output behavior rather than becoming a stale second specification.
- Generated `site/` HTML is an artifact and must not be committed.
- Do not document a PyPI installation unless the project is actually published there and the maintainer explicitly adds that channel.

## Release operations

- Read `DEVELOPMENT.md`, `.github/workflows/docker-publish.yml`, and `x-payloadstash-version-set.sh` before advising on or changing the release process.
- Use the version helper with an unprefixed version such as `1.3.0`; the GitHub Release tag must be the matching `v1.3.0`.
- Ensure the version bump is committed to `main` before the release tag is created. Saving a draft does not publish; publishing the release triggers the workflow.
- Stable releases publish exact, minor, and `latest` tags. Prereleases publish only their exact prerelease tag. Normal `main` commits publish nothing.
- In multi-account environments, verify the active GitHub CLI identity before external actions. Use API host `github.com` even when the repository remote uses a local SSH alias.
- Do not create or publish a release, move or delete a tag, publish an image, or delete package versions without explicit user authorization for that external mutation.
- Treat Buildx untagged platform and provenance records as possible dependencies of a tagged release. Resolve referenced digests before any GHCR cleanup and preserve every release index and its children.

## Validation before completion

For any user-documentation change:

```bash
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/mkdocs build --strict
```

Also compare changed commands with `payloadstash --help` and the affected subcommand help. Validate modified YAML examples with the current CLI or schema tests. When behavior covered by `SKILL.md` changes, review and update it in the same change, validate its complete YAML examples, and run the focused behavior tests (for example, `tests/test_url_operators.py` for `URLRoot`). Run relevant application tests when documentation reflects behavior that changed in code.

For developer-only documentation, run only checks meaningful to the underlying change. When a change spans audiences, validate both the user site and the affected implementation or packaging workflow.

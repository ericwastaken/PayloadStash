# Documentation ownership

PayloadStash separates end-user documentation from repository-facing developer and maintainer documentation.

## Source-of-truth matrix

| Change | Required documentation |
| --- | --- |
| Installation, CLI, configuration, runtime behavior, outputs, examples, or troubleshooting visible to users | Update the applicable Markdown under `docs/`; do not recreate detailed user guides in root or packaged READMEs |
| Developer setup, architecture, tests, contribution workflow, release process, or packaging production | Update the relevant repository Markdown only |
| Change affecting both audiences | Update each source for its audience, keep terminology and links aligned, and avoid copying the same guide into both |
| Configuration/model change | Update `docs/reference/configuration.md`, affected `docs/configuration/` topics, and `config/config-example.yml` when an executable example should change; update developer docs only for implementation/maintenance impact |
| CLI change | Update `docs/reference/cli.md`, affected workflows/examples, and repository developer notes only if development commands change |
| Distribution change | Put artifact-production details in the relevant packaged README and artifact-consumption instructions in `docs/install/` |
| Branding or navigation change | Update `mkdocs.yml`, `docs/assets/` or site styling, and repository links where applicable |

## Boundaries

- `docs/` is the sole source of truth for end-user installation and operation.
- `README.md` is a concise project/developer entry point and links users to GitHub Pages.
- `packaged-python/README - Python Version.md` and `packaged-docker/README - Docker Version.md` describe producing and maintaining artifacts, not using PayloadStash.
- `config/config-example.yml` remains the canonical executable sample; `config/README.md` explains sample-file maintenance.
- Generated `site/` HTML is an artifact and must not be committed.
- Do not document a PyPI installation unless the project is actually published there and the maintainer explicitly adds that channel.

## Validation before completion

For any user-documentation change:

```bash
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/mkdocs build --strict
```

Also compare changed commands with `payloadstash --help` and the affected subcommand help. Validate modified YAML examples with the current CLI or schema tests. Run relevant application tests when documentation reflects behavior that changed in code.

For developer-only documentation, run only checks meaningful to the underlying change. When a change spans audiences, validate both the user site and the affected implementation or packaging workflow.
# Choose an installation

PayloadStash can run from a managed local checkout, a UV-managed clone, a Git-installed UV tool, or the prebuilt container image. PayloadStash is not currently distributed through PyPI.

| Method | Best for | Command | Local source checkout |
| --- | --- | --- | --- |
| [Local bootstrap](local-bootstrap.md) | A self-contained checkout with a project-managed virtual environment | `./payloadstash` | Required |
| [Cloned repository with UV](cloned-uv.md) | Trying the current source or contributing changes | `uv run payloadstash` | Required |
| [GitHub install with UV](git-uv-tool.md) | A native, globally available CLI managed by UV | `payloadstash` | No |
| [GHCR Docker image](docker.md) | Hosts where the application should stay containerized | `docker run ...` | No |

## Common requirements

- Access to the configuration and output directories you intend to use.
- Network access to target HTTP or AMQP services.
- Python 3.8 or newer for native installations, or Docker for the container installation.

After installation, continue with [Create your first configuration](../getting-started/first-config.md).
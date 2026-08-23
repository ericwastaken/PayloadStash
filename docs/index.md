# PayloadStash user guide

<picture class="hero">
    <source media="(max-width: 640px)" srcset="assets/PayloadStash-Banner-Mobile.png">
    <img src="assets/PayloadStash-Banner.png" alt="PayloadStash workflow from YAML and secret injection through HTTP and AMQP to captures, reports, and secret redaction">
</picture>

PayloadStash turns declarative YAML into repeatable HTTP and AMQP workflows. It injects secrets before transport, carries captured values between requests, verifies results with reusable expectations, and writes deterministic evidence for every run.

[Choose an installation](install/index.md){ .md-button .md-button--primary }
[Create your first configuration](getting-started/first-config.md){ .md-button }
[Install the agent skill](agent-skill.md){ .md-button }

!!! tip "Let your coding agent write PayloadStash configurations"
    Download the [PayloadStash agent skill](agent-skill.md) to give a compatible agent current configuration, HTTP, AMQP, capture, expectation, and CLI guidance.

## Why PayloadStash

<div class="grid cards feature-grid" markdown>

-   **One declarative workflow**

    Send HTTP requests and AMQP messages sequentially or concurrently from the same YAML configuration.

    [Configure transports](configuration/index.md)

-   **Secrets enter before transport**

    Inject values from a separate secrets file while redacting loaded values from resolved configuration and run logs.

    [Handle secrets](configuration/secrets-and-dynamic-values.md)

-   **Capture, verify, and continue**

    Carry response values into later requests and make expectations determine the final command status.

    [Capture values](configuration/capture.md) · [Verify results](configuration/expectations.md)

-   **Evidence after every run**

    Retain resolved YAML, response bodies, CSV results, detailed logs, and a readable Markdown report.

    [Inspect run artifacts](reference/output.md)

-   **Container and offline ready**

    Use a GitHub Release, UV-managed installation, GHCR image, or packaged air-gapped Docker workflow.

    [Choose an installation](install/index.md)

</div>

## Find what you need

<div class="grid cards" markdown>

-   :material-download: **Install PayloadStash**

    ---

    Compare GitHub Release, local, cloned, Git-based UV, and Docker installation paths.

    [Installation options](install/index.md)

-   :material-rocket-launch: **Run your first stash**

    ---

    Validate a configuration, inspect resolved values, run requests, and find the report.

    [Getting started](getting-started/first-config.md)

-   :material-file-code: **Configure requests**

    ---

    Define HTTP or AMQP operations, dynamic values, captures, and expectations.

    [Configuration guides](configuration/index.md)

-   :material-lifebuoy: **Solve a problem**

    ---

    Diagnose installation, configuration, connection, and output issues.

    [Troubleshooting](troubleshooting.md)

-   :material-robot: **Equip an AI agent**

    ---

    Install the PayloadStash skill so an agent can create and update configurations with current syntax.

    [Install the agent skill](agent-skill.md)

</div>

!!! info "Looking for developer documentation?"
    Source development, architecture, testing, and packaging documentation remain in the [GitHub repository](https://github.com/ericwastaken/PayloadStash).

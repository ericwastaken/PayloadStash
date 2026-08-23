# PayloadStash user guide

<picture class="hero">
    <source media="(max-width: 640px)" srcset="assets/PayloadStash-Banner-Mobile.png">
    <img src="assets/PayloadStash-Banner.png" alt="PayloadStash workflow from YAML and secret injection through HTTP and AMQP to captures, reports, and secret redaction">
</picture>

PayloadStash turns declarative YAML into a repeatable HTTP and AMQP test suite. Each request or message becomes an executable test case: inject secrets, exercise the target system, carry captured values between operations, verify behavior with reusable expectations, and return an automation-friendly pass or fail result. Deterministic reports and response artifacts preserve the evidence from every run.

[Choose an installation](install/index.md){ .md-button .md-button--primary }
[Build a test suite](getting-started/test-suite.md){ .md-button }

## Why PayloadStash

<div class="grid cards feature-grid" markdown>

-   **A test suite for HTTP and AMQP**

    Exercise APIs, brokers, and integrated systems from one YAML suite. Expectations determine the final process status for local testing or automation.

    [Build a test suite](getting-started/test-suite.md)

-   **Secrets enter before transport**

    Inject values from a separate secrets file while redacting loaded values from resolved configuration and run logs.

    [Handle secrets](configuration/secrets-and-dynamic-values.md)

-   **Capture, verify, and continue**

    Test stateful behavior by carrying response values into later requests and asserting status, data, headers, timing, and AMQP outcomes.

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

    Build and run an HTTP or AMQP test suite, then inspect its pass or fail result and retained evidence.

    [Getting started](getting-started/first-config.md)

-   :material-file-code: **Configure requests**

    ---

    Define HTTP or AMQP operations, dynamic values, captures, and expectations.

    [Configuration guides](configuration/index.md)

-   :material-lifebuoy: **Solve a problem**

    ---

    Diagnose installation, configuration, connection, and output issues.

    [Troubleshooting](troubleshooting.md)

</div>

!!! info "Looking for developer documentation?"
    Source development, architecture, testing, and packaging documentation remain in the [GitHub repository](https://github.com/ericwastaken/PayloadStash).

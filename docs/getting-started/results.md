# Read your first result

Each run creates a UTC timestamped directory below the output root:

```text
output/
└── QuickStart/
    └── 2026-08-22T10-37-00Z/
        ├── quick-start-resolved.yml
        ├── quick-start-results.csv
        ├── quick-start-run.log
        ├── quick-start-report.md
        └── seq001-FetchOneObject/
            └── req001-GetObject-response.json
```

The exact timestamp differs on every run.

## What each artifact contains

- `*-resolved.yml` — the effective redacted configuration used for the run.
- `*-results.csv` — one row per request, including status, duration, attempts, and expectation counts.
- `*-run.log` — chronological request, retry, capture, and error details with loaded secret values redacted.
- `*-report.md` — a readable summary with request/response details and assertion outcomes.
- `seqNNN-*/*-response.<ext>` — response bodies grouped by sequence; the extension follows the response content type.

Open `quick-start-report.md` first for a human-readable result. Use the CSV for automation and the run log for diagnosis.

!!! warning
    Treat output as potentially sensitive. Response bodies and captured values can contain service data even though loaded secret values are redacted from the resolved configuration and log.

See [Output and reports](../reference/output.md) for the complete path and file reference.
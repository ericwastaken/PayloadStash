# Output and reports

`run --out ROOT` writes one UTC timestamped directory for each test-suite execution:

```text
ROOT/<StashConfig.Name>/<RunTimestamp>/
├── <config-stem>-resolved.yml
├── <config-stem>-results.csv
├── <config-stem>-run.log
├── <config-stem>-report.md
└── seqNNN-<Sequence.Name>/
    └── reqNNN-<RequestKey>-response.<ext>
```

Names use sequence/request order and the original configuration stem.

## Run-level artifacts

| File | Contents |
| --- | --- |
| `*-resolved.yml` | Effective configuration, with secret values redacted and deferred markers preserved |
| `*-results.csv` | `sequence`, `request`, `timestamp`, `status`, `duration_ms`, `attempts`, `expect_passed`, `expect_failed` |
| `*-run.log` | Detailed chronological execution, retry, capture, assertion, and error messages |
| `*-report.md` | Human-readable summary and per-request request/response details |

## Response files

One non-empty response body is written per request. The extension follows content type:

| Content type | Typical extension |
| --- | --- |
| JSON | `.json` |
| Plain text | `.txt` |
| CSV | `.csv` |
| XML | `.xml` |
| PDF | `.pdf` |
| Images | format-specific image extension |
| Unknown/missing | `.txt` |

`Response.PrettyPrint` formats JSON/XML, while `Response.Sort` sorts supported structures and implies pretty printing.

## Security and retention

Loaded secrets are redacted from resolved YAML and run logs. Response bodies, request data included in reports, and captured values can still be sensitive. Restrict output directory access and apply an appropriate retention policy.

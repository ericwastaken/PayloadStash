# CLI and exit codes

Use the CLI to validate and execute declarative HTTP/AMQP test suites. Its exit codes let local scripts and automated jobs distinguish a passing suite, failed expectations, and setup errors.

## Global command

```text
payloadstash [--version] COMMAND [ARGS]...
```

| Command | Purpose |
| --- | --- |
| `validate` | Validate and resolve a configuration without sending requests |
| `run` | Validate, resolve, write artifacts, and execute sequences |
| `hello` | Installation smoke test |

## `validate`

```text
payloadstash validate [--writeResolved] [--secrets FILE] CONFIG
```

- `--writeResolved` writes `<config-stem>-resolved.yml` beside `CONFIG`.
- `--secrets FILE` loads case-sensitive `KEY=VALUE` entries needed by operators.
- Success returns `0`; invalid configuration or secret resolution returns `1`.

## `run`

```text
payloadstash run --out DIRECTORY [--dry-run] [--yes] [--secrets FILE] CONFIG
```

- `--out DIRECTORY` is required and becomes the artifact root.
- `--dry-run` resolves and logs without making HTTP requests or AMQP publishes, and without running [script hooks](../configuration/hooks.md); the log lists the hooks that would run.
- `--yes` skips the confirmation prompt.
- `--secrets FILE` loads secret values; written resolved data and logs are redacted.

| Exit code | Meaning |
| --- | --- |
| `0` | The run completed; every `Expect` assertion and hook passed |
| `1` | One or more `Expect` assertions failed, or a `Before` or `Hooks.AfterAll` hook failed |
| `9` | Configuration or output setup failed, or a `Hooks.BeforeAll` hook failed; no requests were sent |

Individual operation errors are recorded and execution continues, so add explicit expectations for statuses that must fail automation.

!!! note
    There is no `payloadstash resolve` command. Use `validate --writeResolved`, or inspect the resolved file written by `run`.

Verify options for the installed version with `payloadstash COMMAND --help`.

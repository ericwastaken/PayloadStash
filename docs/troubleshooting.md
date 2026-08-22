# Troubleshooting

## Command not found

- Bootstrap checkout: run `./payloadstash --help` from the repository root, or rerun `python3 bootstrap.py --reinstall`.
- Cloned UV checkout: use `uv run payloadstash --help`.
- UV tool: run `uv tool update-shell`, open a new shell, and confirm with `uv tool list`.
- Docker: invoke the image with `docker run`; no host `payloadstash` executable is installed.

## `resolve` is not a command

Use:

```bash
payloadstash validate CONFIG.yml --writeResolved
```

`run` also writes a resolved copy into its timestamped output directory.

## Validation fails

Read the reported YAML path and check the [configuration schema](reference/configuration.md). Frequent causes include:

- missing `StashConfig.Name`, sequences, requests, or required flow-control values;
- an HTTP request missing `Method`, `URLPath`, or an effective `URLRoot`;
- an AMQP request missing an effective `URI` or both routing fields;
- `ConcurrencyLimit` on a sequential sequence;
- an unknown field—the schema intentionally rejects extra keys;
- malformed operator syntax or a missing named dynamic/set.

## Secret errors

- “no `--secrets` file” — pass the file to both validation and run.
- “Unknown secret” — keys are case-sensitive; check spelling and file contents.
- Docker file not found — place the file under the mounted directory and pass its container-visible path.

Never paste real secret values into diagnostics. Redaction protects resolved YAML and logs, not arbitrary response bodies.

## HTTP connection or TLS failures

- Confirm the final URL with `validate --writeResolved`.
- Check DNS, proxy/firewall access, service availability, and `TimeoutSeconds`.
- Use retries for transient status/network failures.
- Prefer fixing the certificate chain; reserve `InsecureTLS: true` for controlled tests.

## AMQP publish or wait failures

- Confirm URI encoding, credentials, virtual host, exchange, routing key, and broker reachability.
- PayloadStash does not declare durable application topology; provision exchanges/queues separately.
- `unroutable` with `Mandatory: true` means no queue binding accepted the routing key.
- RPC/subscription timeout means no matching response arrived before `WaitFor.TimeoutSeconds`.
- For private CAs, verify `TLS.CAFile` relative to the process working directory and certificate hostname.

## Output is missing

- `run` requires `--out`; inspect the exact timestamped path printed in its summary.
- Without `--yes`, declining or not answering the confirmation cancels execution.
- Empty response bodies do not produce response-body files.
- In Docker, ensure the output path is inside a bind mount (`/working` for direct GHCR use or `/app/output` for packaged helpers).
- Check permissions on the host output directory.

## Expectations fail

Open `*-report.md` for assertion details and `*-run.log` for the chronology. Confirm response types as well as values: JSON string `"3"` is not numeric `3`. Header paths are case-insensitive; body field names are not.
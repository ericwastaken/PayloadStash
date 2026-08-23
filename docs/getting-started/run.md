# Validate, resolve, and run

The examples below validate and execute a PayloadStash configuration as an HTTP/AMQP test suite. They use an installed `payloadstash` command. Prefix them with `uv run` for a cloned UV checkout, use `./payloadstash` for a bootstrap checkout, or follow the [Docker command form](../install/docker.md).

## Validate

Validation checks the schema and resolves dynamic and secret references without making requests:

```bash
payloadstash validate ./config/quick-start.yml
```

When the configuration references secrets:

```bash
payloadstash validate ./config/quick-start.yml \
  --secrets ./config/secrets.env
```

Success prints the stash name and sequence count. Validation errors exit nonzero and identify the failing configuration path.

## Inspect the resolved configuration

There is no separate `resolve` command. Ask validation to write `<name>-resolved.yml` beside the input file:

```bash
payloadstash validate ./config/quick-start.yml --writeResolved
```

The resolved copy expands YAML anchors, defaults, forced values, and resolve-time operators. Secret values are replaced with `***REDACTED***`.

## Preview a run

`--dry-run` creates the run directory and resolved artifacts but does not send HTTP requests. `run` always requires `--out`.

```bash
payloadstash run ./config/quick-start.yml \
  --out ./output \
  --dry-run \
  --yes
```

## Execute

Remove `--dry-run` to make the requests:

```bash
payloadstash run ./config/quick-start.yml \
  --out ./output \
  --yes
```

Without `--yes`, PayloadStash displays a summary and asks for confirmation. A run continues after an individual test-case error so that later cases can execute; failed expectations make the completed suite exit nonzero.

Now [inspect the generated results](results.md).

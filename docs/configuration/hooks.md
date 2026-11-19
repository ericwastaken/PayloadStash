# Script hooks

Hooks run commands at fixed points of a run, so one configuration can hold a whole test: setup, requests, checks, and cleanup. Use them to check the environment before any request, restart a local service and wait for it, reset state between two sequences, or read an external log after the run.

```yaml
StashConfig:
  Name: returning-user
  Hooks:
    BeforeAll:
      - hooks/check-env.sh
      - { Command: hooks/restart-service.sh, TimeoutSeconds: 120 }   # restart, then wait until it answers
      - hooks/log-mark.sh            # remembers where the external log ends now
    AfterAll:
      - hooks/log-report.sh          # prints the log lines since the mark; exit 1 on a problem
  Defaults:
    URLRoot: https://api.example.com
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
  Sequences:
    - Name: FirstVisit
      Type: Sequential
      Requests:
        - Login:
            Method: POST
            URLPath: /v1/login
            Body: { userId: { $pattern: "USER${hex:16}" }, create: true }
            Capture: { userId: body.userId }
    - Name: ReturningVisit
      Type: Sequential
      Before:
        - hooks/clear-cached-user.sh ${captured:userId}
      Requests:
        - Login:
            Method: POST
            URLPath: /v1/login
            Body: { userId: { $pattern: "${captured:userId}" }, create: false }
```

## When hooks run

| Hook | Where | Runs |
| --- | --- | --- |
| `Hooks.BeforeAll` | `StashConfig` | Once, after the configuration is validated and the run folder exists, before the first sequence |
| `Before` | One sequence | Right before that sequence's first request. For a `Concurrent` sequence, before its workers start |
| `Hooks.AfterAll` | `StashConfig` | Once, after the last sequence that ran, whether requests and `Expect` checks passed or failed |

Each hook is a list of commands that run in order. An empty or missing list runs nothing. The first command that fails stops its list.

## Hook entries

An entry is a command string, or a mapping when the command needs a time limit:

```yaml
BeforeAll:
  - hooks/check-env.sh
  - { Command: hooks/restart-service.sh, TimeoutSeconds: 120 }
```

| Field | Required | Rules |
| --- | --- | --- |
| `Command` | Yes | Non-blank command string |
| `TimeoutSeconds` | No | Number > 0. Without it, the command may run as long as it needs |

When a command exceeds `TimeoutSeconds`, PayloadStash kills it, together with any processes it started, and the hook fails.

## How commands run

- **No shell.** PayloadStash splits the command into arguments with shell-style quoting rules, then runs the program directly. Pipes, redirection, `&&`, and `$VARIABLES` are not interpreted. When you need them, call a shell explicitly, for example `bash -c "docker logs api | tail -n 50"`, or put the logic in a script.
- **Working directory.** Commands run in the configuration file's folder, so `hooks/reset.sh` resolves from there wherever you start PayloadStash. Scripts must be executable (`chmod +x hooks/*.sh`).
- **Environment.** Commands inherit the environment of the `payloadstash` process. PayloadStash adds no variables.

## Captured values and placeholders

A `Before` hook often needs a value an earlier sequence produced, such as the ID of the entity to reset. Pass it as an argument with `${captured:KEY}`:

```yaml
Before:
  - hooks/clear-cached-user.sh ${captured:userId}
```

- Placeholders use the same syntax and engine as [`$pattern` templates](secrets-and-dynamic-values.md). Unlike request fields, a hook command accepts placeholders directly, without `$pattern`.
- The command is split into arguments **before** placeholders are filled in. A captured value with spaces or quotes stays one argument and is never run as shell code.
- A `${captured:KEY}` whose key has not been captured fails the hook: the command does not run, and the run stops as for any failing hook. A key captured as `null` (the response path was missing) counts as missing too. This is stricter than request fields, where a missing key leaves the `${captured:KEY}` text in place.
- `Hooks.BeforeAll` cannot use `${captured:...}`, because nothing has been captured before the first sequence. Validation rejects it.
- `${secrets:KEY}`, `${uuidv4}`, `${hex:N}`, and the other `$pattern` placeholders also work. A secret passed as an argument is visible in the process list while the command runs; prefer an environment variable you set before starting PayloadStash.

## Failures and exit codes

A hook fails when its command exits non-zero, times out, cannot start, or references a captured value that is not available.

| Failing hook | What happens | Exit code |
| --- | --- | --- |
| `BeforeAll` | Its remaining commands do not run, no requests are sent, and `AfterAll` does not run | `9` |
| `Before` | That sequence and all later sequences do not run. `AfterAll` still runs | `1` |
| `AfterAll` | Its remaining commands do not run | `1` |

A failed `AfterAll` never hides a failed `Expect`: either one gives exit code `1`, and the console reports both. See [CLI and exit codes](../reference/cli.md).

## Output

- Each command's standard output and standard error appear in the console as they are written, prefixed with the hook name, for example `[BeforeAll[2]]`.
- `<config-stem>-run.log` records each hook: its name, the command with placeholders filled in, every output line, and the exit code and duration (or why it failed).
- `<config-stem>-report.md` gets a **Hooks** table with each hook's command, result, and duration.
- Secret values loaded with `--secrets` are redacted from hook commands and output in the console, run log, and report. Captured values are not redacted.

Configurations without hooks produce exactly the same output as before.

## Dry runs and validation

- `run --dry-run` runs no hooks. The console and run log list each hook that would run, with placeholders unfilled.
- `validate` checks hook keys and commands: unknown keys, blank commands, unbalanced quotes, `TimeoutSeconds` ≤ 0, `${captured:...}` in `BeforeAll`, and placeholders that cannot be resolved, such as a `${secrets:KEY}` without a secrets file.
- The resolved configuration keeps hook commands as written; placeholders are filled in only when a hook runs.

## Where hooks run

Hooks run wherever PayloadStash runs, with the tools available there. With a native installation (for example `uv run payloadstash ...`), scripts use the machine's own tools.

!!! warning "Docker image"
    In the [GHCR image](../install/docker.md), hooks run inside the container. The image includes `bash`, the core shell tools, Python, `curl`, `jq`, and the Docker CLI, but no database clients, and only mounted folders are visible. To let a hook use the host's Docker, mount the Docker socket; see [Script hooks in the container](../install/docker.md#script-hooks-in-the-container). For other host tools, use a native installation.

# Create your first configuration

A PayloadStash YAML file is both a workflow definition and an executable HTTP/AMQP test suite. It contains a named `StashConfig`, optional defaults and forced values, and one or more sequences of requests or messages that exercise the target system.

## Start from the maintained example

If you cloned the repository, copy its executable sample instead of editing it in place:

```bash
cp config/config-example.yml config/my-config.yml
```

For another installation channel, download [`config/config-example.yml`](https://github.com/ericwastaken/PayloadStash/blob/main/config/config-example.yml) and save it locally.

## Minimal HTTP configuration

This smaller test suite calls a public API and verifies the response:

```yaml
StashConfig:
  Name: QuickStart
  Defaults:
    URLRoot: https://api.restful-api.dev
    FlowControl:
      TimeoutSeconds: 10
  Sequences:
    - Name: FetchOneObject
      Type: Sequential
      Requests:
        - GetObject:
            Method: GET
            URLPath: /objects/7
            Expect:
              - status: 200
              - body: { type: object }
```

Save it as `config/quick-start.yml`. The important pieces are:

- `Name` identifies the run and becomes part of the output path.
- `Defaults.URLRoot` is combined with each request's `URLPath`.
- `Sequences` control ordering and concurrency.
- Each item under `Requests` gives the request a unique name.
- `Expect` assertions turn system behavior into test outcomes and make a failed assertion produce a failed run result.

## Optional secrets file

Secrets files contain case-sensitive `KEY=VALUE` lines:

```dotenv
AUTH_TOKEN=replace-me
```

Reference one without placing its value in YAML:

```yaml
Headers:
  Authorization: "Bearer { $secrets: AUTH_TOKEN }"
```

Pass the file with `--secrets`. Resolved configurations and run logs redact loaded secret values. See [Secrets and dynamic values](../configuration/secrets-and-dynamic-values.md) for the full syntax.

Next, learn [how to structure a test suite](test-suite.md), then [validate and run the configuration](run.md).

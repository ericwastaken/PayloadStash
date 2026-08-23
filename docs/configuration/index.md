# Configuration structure

PayloadStash reads YAML containing optional reusable definitions and one required `StashConfig` object. A configuration can serve as an executable test suite against an HTTP API, an AMQP broker or consumer, or a system that uses both transports.

```yaml
dynamics:                         # optional generated-value definitions
  patterns: {}
  sets: {}

StashConfig:
  Name: Example                   # output and report name
  Defaults:                       # inherited request settings
    URLRoot: https://api.example.com
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10
  Forced:                         # settings applied after request values
    Headers:
      X-Run-Source: payloadstash
  Sequences:
    - Name: HealthChecks
      Type: Sequential
      Requests:
        - Health:
            Method: GET
            URLPath: /health
```

## Resolution model

1. YAML anchors and aliases are resolved by the YAML loader.
2. Request sections inherit from `Defaults` when absent.
3. Request-level values override inherited values where supported.
4. `Forced` values merge last and win on key collisions.
5. Resolve-time operators are expanded; request-time operators remain deferred.
6. Each request is validated as HTTP (default) or AMQP.

Use `payloadstash validate CONFIG --writeResolved` to inspect the effective redacted configuration without sending requests.

## Topic guides

- [HTTP requests](http.md)
- [AMQP requests](amqp.md)
- [Defaults and forced values](precedence.md)
- [Secrets and dynamic values](secrets-and-dynamic-values.md)
- [Sequencing, concurrency, and retries](execution.md)
- [Capture values](capture.md)
- [Expectations](expectations.md)
- [Complete configuration schema](../reference/configuration.md)

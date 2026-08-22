# Defaults and forced values

PayloadStash builds each effective request from three layers.

1. `Defaults` supplies inherited settings.
2. The request supplies its own settings and supported overrides.
3. `Forced` merges last and wins on collisions.

For `Headers`, `Body`, and `Query`, a request section replaces the corresponding default section when present, then `Forced` keys are merged into the result. Nested maps are merged where the schema defines deep merging, notably AMQP configuration and property headers.

```yaml
StashConfig:
  Name: PrecedenceExample
  Defaults:
    URLRoot: https://api.example.com
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
    Headers:
      Accept: application/json
      X-Environment: test
    Body:
      team: blue
  Forced:
    Headers:
      X-Environment: production
    Body:
      team: green
  Sequences:
    - Name: Demo
      Type: Sequential
      Requests:
        - Send:
            Method: POST
            URLPath: /items
            Headers:
              Content-Type: application/json
            Body:
              name: example
              team: red
```

The effective request has request-defined `Content-Type`, forced `X-Environment: production`, request-defined `name`, and forced `team: green`. Because the request supplied `Headers`, the default `Accept` header is not copied automatically; use YAML anchors when you want explicit reusable maps.

## YAML anchors

YAML anchors are handled before PayloadStash applies its own layers:

```yaml
common_headers: &common_headers
  Accept: application/json
  Content-Type: application/json

Headers:
  <<: *common_headers
  X-Request-Scope: catalog
```

Inspect the final result with `payloadstash validate CONFIG --writeResolved`.

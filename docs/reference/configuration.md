# Configuration schema

Field names and enum values are case-sensitive. Unknown fields inside modeled configuration objects are rejected; unrelated top-level YAML keys may be used for anchors and are otherwise ignored.

## Top level

| Field | Required | Type | Description |
| --- | --- | --- | --- |
| `StashConfig` | Yes | object | Run definition |
| `dynamics` | No | object | Reusable generated-value patterns and sets |

### `dynamics`

```yaml
dynamics:
  patterns:
    name:
      template: "user-${alpha:6}"
  sets:
    region: [na, eu]
```

`patterns` maps unique names to objects with a required string `template`. Optional `sets` maps names to lists of strings. Request-level `dynamics` may add or override patterns and sets for that request.

## `StashConfig`

| Field | Required | Type | Rules |
| --- | --- | --- | --- |
| `Name` | Yes | non-empty string | Used in output paths and reports |
| `Defaults` | Yes | defaults object | Base HTTP/AMQP and execution settings |
| `Forced` | No | forced object | Final overlay applied to every compatible request |
| `Sequences` | Yes | non-empty list | Sequence names must be unique |

## Defaults and forced fields

| Field | `Defaults` | `Forced` | Type |
| --- | --- | --- | --- |
| `URLRoot` | Optional, conditionally required | — | non-blank string or value operator |
| `FlowControl` | Required | — | flow-control object |
| `InsecureTLS` | Optional | — | boolean; default `false` |
| `Headers` | Optional | Optional | map |
| `Body` | Optional | Optional | map |
| `Query` | Optional | Optional | map |
| `Retry` | Optional | Optional | retry object or `null` |
| `Response` | Optional | — | response object |
| `AMQP` | Optional | Optional | AMQP object |

`Defaults.URLRoot` is required when any HTTP request omits its own `URLRoot`. Although some empty flow-control mappings can pass model parsing, always provide both required fields; execution relies on effective values.

### `FlowControl`

| Field | Defaults | Request override |
| --- | --- | --- |
| `DelaySeconds` | Required integer ≥ 0 | Optional integer ≥ 0 |
| `TimeoutSeconds` | Required integer ≥ 0 | Optional integer ≥ 0 |

### `Retry`

| Field | Required | Type/default |
| --- | --- | --- |
| `Attempts` | Yes | integer ≥ 1; total attempts including first |
| `BackoffStrategy` | Yes | `fixed` or `exponential` |
| `BackoffSeconds` | Yes | number ≥ 0 |
| `Multiplier` | No | number ≥ 1; default `2` |
| `MaxBackoffSeconds` | No | number ≥ 0 |
| `MaxElapsedSeconds` | No | number ≥ 0 |
| `Jitter` | No | boolean, `min`, or `max` |
| `RetryOnStatus` | No | list of HTTP status integers |
| `RetryOnNetworkErrors` | No | boolean; default `true` |
| `RetryOnTimeouts` | No | boolean; default `true` |

Use `Retry: null` to disable an inherited retry policy. A request-level retry value—including explicit `null`—takes precedence over `Defaults`; `Forced.Retry` is applied last.

### `Response`

`PrettyPrint` and `Sort` are optional booleans. `Sort: true` implies pretty printing for supported JSON/XML responses.

## Sequences

| Field | Required | Rules |
| --- | --- | --- |
| `Name` | Yes | Non-empty and unique within the run |
| `Type` | Yes | `Sequential` or `Concurrent` |
| `ConcurrencyLimit` | Conditional | Integer ≥ 1; required for `Concurrent`, forbidden for `Sequential` |
| `Requests` | Yes | Non-empty list of single-key request maps |

Each request item has exactly one request name:

```yaml
Requests:
  - RequestName:
      Transport: http
      Method: GET
      URLPath: /health
```

## HTTP request

`Transport` defaults to `http` and may be omitted.

| Field | Required | Type/rules |
| --- | --- | --- |
| `Transport` | No | `http` |
| `Method` | Yes | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| `URLPath` | Yes | non-blank string or supported value operator |
| `URLRoot` | Conditional | request override; omission inherits, explicit `null` is invalid |
| `Headers`, `Body`, `Query` | No | maps |
| `FlowControl` | No | partial flow-control override |
| `Retry` | No | retry object or `null` |
| `Response` | No | response object |
| `InsecureTLS` | No | boolean |
| `Capture` | No | map of capture names to paths/JSONPath operators |
| `Expect` | No | list of assertions |
| `dynamics` | No | request-local dynamics |

## AMQP request

```yaml
- Publish:
    Transport: amqp
    AMQP:
      URI: amqp://guest:guest@localhost:5672/%2F
      Exchange: events
      RoutingKey: item.created
    Body: { id: 1 }
```

| Field | Required | Type/rules |
| --- | --- | --- |
| `Transport` | Yes | `amqp` |
| `AMQP` | Yes | AMQP object; effective URI and routing required |
| `Body` | No | message payload, serialized as JSON when structured |
| `FlowControl` | No | partial override |
| `Retry` | No | retry object or `null` |
| `Capture`, `Expect`, `dynamics` | No | same response-processing concepts as HTTP |

HTTP-only fields (`Method`, `URLPath`, `URLRoot`, `Headers`, `Query`, `InsecureTLS`, `Response`) are invalid on AMQP requests.

### `AMQP`

| Field | Required | Type/rules |
| --- | --- | --- |
| `URI` | Effective value required | broker URI; supports secret operator |
| `Exchange` | Conditional | string; defaults to empty |
| `RoutingKey` | Conditional | string |
| `Confirm` | No | boolean |
| `Mandatory` | No | boolean |
| `Properties` | No | message-properties object |
| `TLS` | No | TLS object |
| `WaitFor` | No | publish-and-wait object |

At least one of effective `Exchange` or `RoutingKey` must be non-empty.

Message properties are `ContentType`, `ContentEncoding`, `DeliveryMode` (`transient`/`persistent`), `Priority` (0–9), `CorrelationId`, `ReplyTo`, `Expiration`, `MessageId`, `Type`, `AppId`, and `Headers`. The implementation coerces several property values to broker-compatible strings.

TLS fields are `CAFile`, `CAPath`, `CertFile`, `KeyFile`, `VerifyPeer`, and `ServerName`. Explicitly set `VerifyPeer: true` when peer verification is required rather than relying on an implicit value.

### `WaitFor`

| Field | `rpc` | `subscribe` |
| --- | --- | --- |
| `Mode` | `rpc` | `subscribe` |
| `TimeoutSeconds` | Optional non-negative number | Optional non-negative number |
| `Exchange` | Not used | Required |
| `RoutingKey` | Not used | Optional |
| `Match` | Not used | Required expectation list |

When omitted, wait timing follows the effective operation timeout. RPC creates a reply queue and correlation ID; subscribe binds a temporary queue before publishing.

## Capture and expectations

`Capture` values are either simple path strings or `{ $jsonpath: EXPRESSION }`. `Expect` is a list of single-key `{ path: matcher }` maps. See [Capture values](../configuration/capture.md) and [Expectations](../configuration/expectations.md) for paths, aggregations, and matchers.

## Value operators

Supported mapping forms include:

```yaml
secret: { $secrets: KEY }
dynamic: { $dynamic: pattern_name, when: request }
timestamp: { $timestamp: { format: epoch_ms, when: request } }
function: { $func: timestamp, format: iso_8601 }
pattern: { $pattern: "id-${uuidv4}" }
```

`when` is `resolve` (default) or `request`. `$pattern` is always request-time. The timestamp `$func` accepts `format` (and the implementation also accepts `fmt`); prefer `format` for portability and clarity.

## Merge summary

- Precedence is `Forced` > request > `Defaults`.
- Request `Headers`, `Body`, and `Query` replace their default section when present; forced keys overlay the selected map.
- AMQP objects merge defaults → request → forced, with a deep merge for `Properties.Headers`.
- Request-local dynamics override top-level patterns/sets of the same name.
- Resolve-time operators appear as values in resolved output; request-time values remain deferred markers.
# Expectations

An `Expect` list defines the assertions for an HTTP or AMQP test case. PayloadStash evaluates every assertion after the operation, and any failed assertion makes the completed test-suite run exit with code `1`.

```yaml
Expect:
  - status: 200
  - body.id: { exists: true }
  - body.name: { type: string }
  - headers.content-type: { matches: "application/json" }
  - duration_ms: { lte: 2000 }
```

A primitive value is shorthand for `equals`. Paths use the same simple and JSONPath forms as [Capture](capture.md).

## Matchers

| Matcher | Meaning |
| --- | --- |
| `equals`, `notEquals` | Deep equality or inequality |
| `exists` | Presence/non-null check when `true`; missing/null check when `false` |
| `type` | `string`, `number`, `integer`, `boolean`, `object`, `array`, or `null` |
| `matches`, `notMatches` | Regular-expression test on the string value |
| `contains`, `notContains` | Substring or array membership |
| `in`, `notIn` | Membership in a supplied list |
| `lengthEquals`, `lengthGte`, `lengthLte` | String or array length |
| `gt`, `gte`, `lt`, `lte` | Numeric comparison |

## JSONPath and captures

```yaml
Expect:
  - '$.items[?(@.role=="admin")].id': { exists: true }
  - '$.items[*].score::sum': { gte: 50 }
  - body.id: { equals: { $pattern: "${captured:expectedId}" } }
```

For AMQP, assert publish statuses such as `ack`, `published`, `unroutable`, `reply`, or `matched`, and inspect synthesized `headers.x-amqp-*` metadata.

!!! tip
    A transport error alone does not necessarily determine the final process status. Treat expectations as the test contract: assert every status, response field, header, timing limit, or AMQP outcome that must make the suite fail.

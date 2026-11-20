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
| `unique` | `true`: the array has no repeated elements; `false`: it has at least one |
| `setEquals` | The array holds exactly the listed elements, in any order (repeats ignored) |
| `containsAll` | The array holds every listed element, in any order |
| `keysEqual` | The object's keys are exactly the listed names, in any order |

The collection matchers compare objects and arrays by value, so `{a: 1, b: 2}` and `{b: 2, a: 1}` are the same element. A failure lists the elements that are missing, unexpected, or repeated:

```yaml
Expect:
  - body.team: { unique: true, lengthLte: 5 }
  - "$.items[*].id": { setEquals: [a, b, c] }
  - body.roles: { containsAll: [reader] }
  - body.profile: { keysEqual: [id, name, avatar] }
```

On a JSONPath that can match many nodes (`[*]`, `.*`, a filter `[?(...)]`, a slice, `..` or a union), `unique`, `setEquals` and `containsAll` see every match as a list: one match is a one-element list and no match is an empty list, so `"$.items[?(@.class=='x')].id": { setEquals: [] }` asserts that nothing matches. A path to one node (`body.team`, `$.team`, `$.a[0].tags`) is the value at that node, so it must be an array. Other matchers on the same path still see a scalar for one match and `null` for none.

`validate` rejects a collection matcher whose expected value has the wrong shape, for example `setEquals: a`.

## JSONPath and captures

```yaml
Expect:
  - '$.items[?(@.role=="admin")].id': { exists: true }
  - '$.items[*].score::sum': { gte: 50 }
  - body.id: { equals: { $pattern: "${captured:expectedId}" } }
```

`${captured:KEY}` inside `$pattern` always produces a string. To compare against a captured number, list or object with its original type, use `$captured`:

```yaml
- Before:
    Method: GET
    URLPath: /player
    Capture:
      points: body.points          # 120 (a number)
      team: body.team              # [u1, u2] (a list)
- After:
    Method: GET
    URLPath: /player
    Expect:
      - body.points: { gte: { $captured: points } }
      - body.team: { equals: { $captured: team } }
      - body.team: { setEquals: { $captured: team } }
```

A name that has not been captured resolves to `null`. `$captured` works anywhere `$pattern` does, so it can also send a captured list or object in a later `Body`.

## Values from the same response

An expected value of `{ $jsonpath: EXPRESSION }` is read from the response being checked, so two fields of one response can be compared:

```yaml
Expect:
  - body.total: { equals: { $jsonpath: "$.items[*].amount::sum" } }
  - body.lead: { equals: { $jsonpath: "$.order[0]" } }
  - body.order: { containsAll: { $jsonpath: "$.team" } }
```

The expression uses the same resolver as `Capture`, including filters and `::` aggregations. As there, one match yields a scalar; the exception is an expected value for `unique`, `setEquals` or `containsAll`, which follows the list rule above. A failure shows both values: `actual: 11  expected ($.items[*].amount::sum): 12`.

## Defaults for every request

`Defaults.Expect` is applied to every HTTP and AMQP request, before the request's own `Expect`. A request opts out with `SkipDefaultExpect: true`:

```yaml
Defaults:
  URLRoot: https://api.example.com
  FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
  Expect:
    - status: 200
    - headers.content-type: { matches: json }
Sequences:
  - Name: Checks
    Type: Sequential
    Requests:
      - GetItem:
          Method: GET
          URLPath: /items/1            # checked by Defaults.Expect only
      - MissingItem:
          Method: GET
          URLPath: /items/does-not-exist
          SkipDefaultExpect: true
          Expect:
            - status: 404
```

The resolved configuration shows the combined list on each request.

## Retrying until expectations pass

To poll an eventually consistent endpoint, set `RetryOnExpectFailure: true` in the request's `Retry` policy. The request is re-sent until every assertion passes or the attempts or `MaxElapsedSeconds` run out, with request-time values (`when: request`, `$pattern`) generated afresh for each attempt; see [Retry policy](execution.md#retry-policy). Set it on the request, not in `Defaults.Retry`: inherited from there, it makes every HTTP request with an expectation poll, writes included.

```yaml
- WaitForSync:
    Method: GET
    URLPath: /mirror/player/42
    Retry:
      Attempts: 30
      BackoffStrategy: fixed
      BackoffSeconds: 2
      MaxElapsedSeconds: 60
      RetryOnExpectFailure: true
    Expect:
      - body.synced: true
      - body.points: { equals: { $captured: points } }
```

## Sequence expectations

A sequence may carry its own `Expect` list, evaluated once after all of its requests have finished. Its paths are JSONPath expressions over this document:

```json
{
  "captured": { "KEY": "value, for every capture in the run so far" },
  "requests": [
    { "key": "RequestName", "status": 200, "duration_ms": 41, "headers": {}, "body": {} }
  ]
}
```

`requests` is in the order the requests are listed, and `body` is the parsed JSON body when possible. This checks properties that span several responses, such as concurrent requests where exactly one should win:

```yaml
- Name: ConcurrentPairing
  Type: Concurrent
  ConcurrencyLimit: 5
  Requests:
    - Pair1: { Method: POST, URLPath: /pair, Body: { device: a } }
    - Pair2: { Method: POST, URLPath: /pair, Body: { device: b } }
    - Pair3: { Method: POST, URLPath: /pair, Body: { device: c } }
  Expect:
    - "$.requests[?(@.body.merge.status=='merged')]::count": { equals: 1 }
    - "$.requests[*].status": { setEquals: [200] }
    - "$.captured.pointsAfter": { gte: { $captured: pointsBefore } }
```

Sequence results appear in the log, the CSV (request `<Name> (sequence)`) and the report, and failures count toward the exit code. `Defaults.Expect` does not apply to sequence expectations, and a dry run skips them.

For AMQP, assert publish statuses such as `ack`, `published`, `unroutable`, `reply`, or `matched`, and inspect synthesized `headers.x-amqp-*` metadata.

!!! tip
    A transport error alone does not necessarily determine the final process status. Treat expectations as the test contract: assert every status, response field, header, timing limit, or AMQP outcome that must make the suite fail.

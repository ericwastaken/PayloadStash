# Capture values

`Capture` stores response values in a run-level dictionary. Later requests can interpolate them with `${captured:KEY}` inside `$pattern`.

```yaml
- CreateThing:
    Method: POST
    URLPath: /things
    Body: { name: demo }
    Capture:
      thingId: body.id
      etag: headers.ETag
      elapsed: duration_ms
- ReadThing:
    Method: GET
    URLPath: /things/placeholder
    Headers:
      If-Match: { $pattern: "${captured:etag}" }
    Query:
      id: { $pattern: "${captured:thingId}" }
```

## Simple paths

| Path | Value |
| --- | --- |
| `status` | HTTP or AMQP status |
| `duration_ms` | Operation duration in milliseconds |
| `headers.NAME` | Response metadata/header, matched case-insensitively |
| `body` | Entire parsed body |
| `body.field` | Dot path into parsed JSON |
| `body[N].field` | Indexed array path |

Missing paths capture `null`. Captures are most predictable in sequential sequences; do not create ordering dependencies between concurrently executed requests.

## JSONPath

Use `$jsonpath` for filters, wildcards, or aggregation:

```yaml
Capture:
  firstId: { $jsonpath: "$.items[*].id::first" }
  allIds: { $jsonpath: "$.items[*].id" }
  count: { $jsonpath: "$.items[*]::count" }
  total: { $jsonpath: "$.items[*].score::sum" }
```

Suffixes are `::first`, `::last`, `::count`, `::sum`, `::avg`, `::min`, and `::max`. Without a suffix, one match returns a scalar and multiple matches return a list.

Expectations are evaluated before captures for the same response. A capture from one request is therefore available only to later requests.
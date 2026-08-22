# HTTP requests

HTTP is the default transport. An HTTP request needs `Method` and `URLPath`, plus a `URLRoot` inherited from `Defaults` or supplied on the request.

```yaml
StashConfig:
  Name: HttpExample
  Defaults:
    URLRoot: https://api.example.com/v1
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 15 }
    Headers:
      Accept: application/json
  Sequences:
    - Name: CreateAndRead
      Type: Sequential
      Requests:
        - Create:
            Method: POST
            URLPath: /things
            Headers:
              Content-Type: application/json
            Query:
              notify: true
            Body:
              name: demo
            Expect:
              - status: 201
```

## URL construction

PayloadStash joins `URLRoot.rstrip('/')` and `URLPath.lstrip('/')` with one slash. A request can override the default root:

```yaml
URLRoot: https://status.example.net
URLPath: /health
```

Both fields support value operators such as `$secrets`, `$dynamic`, `$pattern`, `$timestamp`, and `$func`. Explicit `null` is invalid for a request `URLRoot`; omit it to inherit the default.

## Request fields

| Field | Purpose |
| --- | --- |
| `Method` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, or `OPTIONS` |
| `Headers` | HTTP header map; response header lookup is case-insensitive |
| `Query` | Query-string values; lists produce repeated values where supported |
| `Body` | Request body data, commonly serialized as JSON |
| `InsecureTLS` | Disable certificate verification; use only for controlled testing |
| `FlowControl` | Override delay or timeout |
| `Retry` | Override or disable the inherited retry policy |
| `Response` | Control pretty printing and sorting of JSON/XML output |
| `Capture` / `Expect` | Extract and verify response values |

!!! warning "TLS verification"
    `InsecureTLS: true` weakens connection security. Prefer a valid service certificate in production.

## Response formatting

Set `Response.PrettyPrint: true` for formatted JSON or XML. `Response.Sort: true` also sorts JSON object keys or XML children/attributes and implies pretty printing. Other content types are written unchanged.
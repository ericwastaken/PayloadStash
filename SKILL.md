# Skill: Write a PayloadStash Config File

Use this skill when asked to create, edit, or extend a PayloadStash YAML config file.

---

## What PayloadStash Does

PayloadStash reads a YAML config, executes HTTP requests (sequentially or concurrently), writes each response to disk, and optionally asserts on response values. Every run produces a resolved config, a run log, a results CSV, and a markdown report.

---

## File Structure

```yaml
# Optional: YAML anchors for reuse
my_headers: &my_headers
  Content-Type: application/json

# Optional: dynamic value generators
dynamics:
  patterns:
    myId:
      template: "ID-${hex:8}"
  sets:
    envs: ["stage", "prod"]

# Required: the config body
StashConfig:
  Name: MyRun                  # required, unique run name
  Defaults: ...                # required
  Forced: ...                  # optional
  Sequences: [...]             # required, non-empty list
```

Top-level keys outside `StashConfig` and `dynamics` are ignored by the parser — use them freely for YAML anchors.

---

## Defaults (required)

```yaml
Defaults:
  URLRoot: https://api.example.com   # required, no trailing slash
  FlowControl:                        # required
    DelaySeconds: 0                   # int >= 0
    TimeoutSeconds: 30                # int >= 0
  InsecureTLS: false                  # optional; skips TLS verification
  Headers:                            # optional
    Content-Type: application/json
  Body:                               # optional
    commonField: value
  Query:                              # optional
    version: v2
  Retry:                              # optional; see Retry section
    Attempts: 3
    BackoffStrategy: exponential
    BackoffSeconds: 0.5
  Response:                           # optional
    PrettyPrint: true
    Sort: false
```

---

## Forced (optional)

Keys in `Forced` are overlaid on top of Defaults and per-request values last. Use it to inject values that must always win (e.g., an auth header that cannot be overridden by individual requests).

```yaml
Forced:
  Headers:
    Authorization: { $secrets: TOKEN }
  Body:
    tenantId: "acme"
  Query: ...
  Retry: ...
```

---

## Sequences

Each sequence is a named group of requests that run either sequentially or concurrently.

```yaml
Sequences:
  - Name: MySequence          # required; unique across all sequences
    Type: Sequential          # Sequential | Concurrent
    # ConcurrencyLimit: 4     # required when Type=Concurrent; forbidden when Sequential
    Requests:
      - RequestKey:           # unique within this sequence; used in filenames and reports
          Method: POST        # GET | POST | PUT | PATCH | DELETE | HEAD | OPTIONS
          URLPath: /v1/thing  # appended to URLRoot
          Headers: ...        # optional; overrides Defaults.Headers
          Body: ...           # optional; overrides Defaults.Body
          Query: ...          # optional; overrides Defaults.Query
          FlowControl: ...    # optional; overrides Defaults.FlowControl fields
          Retry: ...          # optional; set to Null to disable retries for this request
          Response: ...       # optional; overrides Defaults.Response
          InsecureTLS: false  # optional; overrides Defaults.InsecureTLS
          dynamics: ...       # optional; request-level patterns merged with top-level
          Capture: ...        # optional; extract values from the response
          Expect: ...         # optional; assert on the response
```

**Merge rules for Headers / Body / Query:**
- Start with the request-level value if present; otherwise use Defaults.
- Overlay Forced on top last.

**Retry precedence:**
- `request.Retry` (even if `Null`) beats `Defaults.Retry`.
- Only falls through to Defaults when the request omits `Retry` entirely.

---

## Retry

```yaml
Retry:
  Attempts: 3                         # int >= 1 (total tries including first)
  BackoffStrategy: exponential        # fixed | exponential
  BackoffSeconds: 0.5                 # float >= 0; base delay
  Multiplier: 2.0                     # float > 0; only for exponential (default 2.0)
  MaxBackoffSeconds: 10.0             # float >= 0; cap per-retry delay
  MaxElapsedSeconds: 60.0             # float >= 0; total budget across all retries
  Jitter: true                        # bool or "min" | "max"
  RetryOnStatus: [429, 500, 502, 503, 504]
  RetryOnNetworkErrors: true
  RetryOnTimeouts: true
```

Disable retries for a specific request with `Retry: Null`.

---

## Response Formatting

```yaml
Response:
  PrettyPrint: true   # pretty-print JSON (via Rich) and XML before writing to file
  Sort: true          # sort JSON keys / XML elements; implies PrettyPrint
```

---

## Special Operators

### `$dynamic` — named pattern from the dynamics section

```yaml
# resolve-time (default): same value used everywhere the pattern appears in this run
Body:
  id: { $dynamic: myId }

# request-time: fresh value generated right before each HTTP call
Body:
  id: { $dynamic: myId, when: request }
```

Requires a `dynamics.patterns.<name>.template` entry at the top of the file (or in the request's own `dynamics` block).

### `$pattern` — inline request-time template

Always evaluated at request time — no `when` key needed or accepted. Use this for one-off templates that don't need a named pattern, and for accessing captured values from previous responses.

```yaml
Body:
  traceId:  { $pattern: "${hex:16}" }
  parentId: { $pattern: "${captured:thingId}" }   # captured ref from a prior request
  env:      { $pattern: "${choice:envs}" }         # needs dynamics.sets.envs
```

### `$secrets` — inject a secret from the --secrets file

```yaml
# mapping form (preferred)
Headers:
  Authorization: { $secrets: API_TOKEN }

# inline string form
Headers:
  Authorization: "Bearer { $secrets: API_TOKEN }"
```

### `$timestamp` — current UTC timestamp

```yaml
# shorthand (preferred)
Body:
  ts: { $timestamp: epoch_ms }     # epoch_ms | epoch_s | iso_8601

# deferred to request time
Body:
  ts: { $timestamp: { format: epoch_ms, when: request } }
```

---

## Dynamics Patterns

Define named generators at the top of the file. Each pattern has a `template` string with placeholders.

```yaml
dynamics:
  patterns:
    resourceId:
      template: "RES-${uuidv4}"
    bandId:
      template: "011${hex:34}"
    label:
      template: "probe-${timestamp:epoch_ms}"
    env:
      template: "${choice:envs}"
  sets:
    envs: ["stage", "prod", "dev"]
```

**Available placeholders inside templates and inside `$pattern`:**

| Placeholder | Output |
|---|---|
| `${hex:N}` | N random uppercase hex chars (0–9, A–F) |
| `${alphanumeric:N}` | N random chars (0–9, A–Z, a–z) |
| `${numeric:N}` | N random digits |
| `${alpha:N}` | N random letters (A–Z, a–z) |
| `${uuidv4}` | UUID v4 string |
| `${choice:setName}` | One random element from `dynamics.sets[setName]` |
| `${timestamp[:format]}` | UTC timestamp; format: `epoch_ms` \| `epoch_s` \| `iso_8601` |
| `${secrets:KEY}` | Value from the --secrets file |
| `${captured:KEY}` | Value captured from a prior response — **only valid inside `$pattern`** |

**resolve vs. request timing (for `$dynamic`):**
- `when: resolve` (default): evaluated once at config load time. All references share the same value.
- `when: request`: fresh value generated right before each HTTP call.

`$pattern` is always request-time — no `when` key.

### Request-level dynamics

A request can define its own `dynamics` block. Its patterns merge with (and override) the top-level patterns for that request only.

```yaml
- CreateThing:
    Method: POST
    URLPath: /v1/things
    dynamics:
      patterns:
        localId:
          template: "LOCAL-${hex:8}"
    Body:
      id: { $dynamic: localId }
```

---

## Capture

Extract values from a response and make them available to later requests via `$pattern`.

```yaml
- CreateThing:
    Method: POST
    URLPath: /v1/things
    Body:
      name: widget
    Capture:
      thingId: body.id          # dot path into parsed JSON body
      thingUrl: body.links.self
      responseStatus: status
      serverTime: headers.x-timestamp
      elapsed: duration_ms
```

**Supported path prefixes:**

| Path | Resolves to |
|---|---|
| `status` | HTTP status code (int) |
| `duration_ms` | Request duration in milliseconds (int) |
| `headers.<name>` | Response header value (lowercase key) |
| `body` | Entire parsed response body |
| `body.<field>` | Dot-notation path into parsed JSON |
| `body[N].<field>` | Array index into parsed JSON |

### `$jsonpath` operator

For complex extractions — filter predicates, wildcards, multi-match — use the `$jsonpath` operator instead of a plain path string. The `$` root refers to the parsed response body.

```yaml
Capture:
  thingId: body.id                                                    # simple path (unchanged)
  matchedValue: { $jsonpath: '$.items[?(@.id=="DYX")].value' }       # filter by field value
  allIds:        { $jsonpath: '$.items[*].id' }                       # wildcard → list
  totalScore:    { $jsonpath: '$.players[*].score::sum' }             # aggregation
  playerCount:   { $jsonpath: '$.players[*]::count' }
  topScore:      { $jsonpath: '$.players[*].score::max' }
  firstItem:     { $jsonpath: '$.items[*].id::first' }
  lastItem:      { $jsonpath: '$.items[*].id::last' }
```

**Aggregation suffixes** (append `::suffix` to the JSONPath expression):

| Suffix | Behaviour |
|---|---|
| `::first` | First match |
| `::last` | Last match |
| `::count` | Number of matches |
| `::sum` | Sum of numeric matches |
| `::avg` | Average of numeric matches |
| `::max` | Maximum of numeric matches |
| `::min` | Minimum of numeric matches |

Without a suffix: a single match returns a scalar; multiple matches return a list.

### Using captured values

Reference captured values in any later request field using `{ $pattern: "${captured:KEY}" }`:

```yaml
- GetThing:
    Method: GET
    URLPath: /v1/things/123
    Headers:
      X-Correlation-Id: { $pattern: "${captured:thingId}" }
    Body:
      parentId: { $pattern: "${captured:thingId}" }
    Expect:
      - body.id: { equals: { $pattern: "${captured:thingId}" } }
```

`${captured:KEY}` is resolved just before the request fires, so it always sees values written by previously executed requests. It is **only valid inside a `$pattern` template** — not in plain strings.

---

## Expect

Assert on response values. All assertions run — no short-circuit on first failure.

```yaml
- GetThing:
    Method: GET
    URLPath: /v1/things/123
    Expect:
      - status: 200                              # shorthand for { equals: 200 }
      - body.id: { equals: "123" }
      - body.name: { exists: true }
      - body.deletedAt: { exists: false }
      - body.name: { type: string }
      - body.items: { type: array }
      - body.count: { gt: 0 }
      - body.score: { gte: 0.5 }
      - body.retries: { lt: 5 }
      - body.retries: { lte: 4 }
      - body.id: { matches: "^[A-Z0-9]+$" }
      - body.id: { notMatches: "^[a-z]" }
      - body.tags: { contains: "featured" }
      - body.tags: { notContains: "archived" }
      - status: { in: [200, 201] }
      - status: { notIn: [400, 403, 404, 500] }
      - body.items: { lengthEquals: 3 }
      - body.items: { lengthGte: 1 }
      - body.items: { lengthLte: 10 }
      - duration_ms: { lt: 5000 }
      - headers.content-type: { contains: "application/json" }
```

**Full matcher reference:**

| Matcher | Value type | Meaning |
|---|---|---|
| `equals` / `notEquals` | any | Deep equality |
| `exists` | bool | `true` = not null/missing; `false` = null/missing |
| `type` | string | `string` \| `number` \| `integer` \| `boolean` \| `object` \| `array` \| `null` |
| `matches` / `notMatches` | regex string | Stringified value tested against regex |
| `contains` / `notContains` | string or element | Substring in string, or element in array |
| `in` / `notIn` | list | Value is/is not in the list |
| `lengthEquals` / `lengthGte` / `lengthLte` | int | Array or string length |
| `gt` / `gte` / `lt` / `lte` | number | Numeric comparison |

Shorthand: a primitive value (`status: 200`) is sugar for `{ equals: 200 }`.

**Expect with captured values:**

```yaml
- VerifyThing:
    Method: GET
    URLPath: /v1/things/123
    Expect:
      - status: 200
      - body.id: { equals: { $pattern: "${captured:thingId}" } }
```

---

## YAML Anchors and Merge Keys

Anchors (`&name`) and aliases (`*name`) work anywhere. Merge keys (`<<`) combine maps.

```yaml
common_headers: &common_headers
  Content-Type: application/json
  Accept: application/json

auth_headers: &auth_headers
  Authorization: { $secrets: TOKEN }

Defaults:
  Headers:
    <<: [*common_headers, *auth_headers]   # merge multiple anchors
    X-Client: payloadstash
```

---

## Common Patterns

### Create then read

```yaml
- CreateUser:
    Method: POST
    URLPath: /users
    Body:
      email: test@example.com
    Capture:
      userId: body.id
    Expect:
      - status: 201
      - body.id: { exists: true }

- GetUser:
    Method: GET
    URLPath: /users/123
    Headers:
      X-User-Id: { $pattern: "${captured:userId}" }
    Expect:
      - status: 200
      - body.id: { equals: { $pattern: "${captured:userId}" } }
      - body.email: { equals: "test@example.com" }
```

### Same request against multiple environments

```yaml
dynamics:
  patterns:
    host:
      template: "${choice:hosts}"
  sets:
    hosts: ["https://stage.api.example.com", "https://prod.api.example.com"]
```

### Disable retry for one request

```yaml
- QuickCheck:
    Method: GET
    URLPath: /health
    Retry: Null
```

### Per-request timeout override

```yaml
- SlowExport:
    Method: POST
    URLPath: /export
    FlowControl:
      TimeoutSeconds: 120
```

### Concurrent fan-out

```yaml
- Name: FanOut
  Type: Concurrent
  ConcurrencyLimit: 5
  Requests:
    - CheckA:
        Method: GET
        URLPath: /v1/a
    - CheckB:
        Method: GET
        URLPath: /v1/b
    - CheckC:
        Method: GET
        URLPath: /v1/c
```

---

## Full Working Example

A realistic config using anchors, dynamics, secrets, Capture, Expect, `$pattern`, a sequential sequence, and a concurrent sequence.

```yaml
common_headers: &common_headers
  Content-Type: application/json
  Accept: application/json

dynamics:
  patterns:
    requestId:
      template: "REQ-${uuidv4}"
    env:
      template: "${choice:envs}"
  sets:
    envs: ["stage", "prod"]

StashConfig:
  Name: WidgetServiceRun

  Defaults:
    URLRoot: https://api.example.com
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 30
    Headers:
      <<: *common_headers
      X-Request-Id: { $dynamic: requestId }
    Retry:
      Attempts: 3
      BackoffStrategy: exponential
      BackoffSeconds: 0.5
      RetryOnStatus: [429, 502, 503, 504]
    Response:
      PrettyPrint: true

  Forced:
    Headers:
      Authorization: { $secrets: API_TOKEN }

  Sequences:

    - Name: CreateAndVerify
      Type: Sequential
      Requests:

        - CreateWidget:
            Method: POST
            URLPath: /v1/widgets
            Body:
              name: "test-widget"
              env: { $dynamic: env }
            Capture:
              widgetId: body.id
              widgetName: body.name
            Expect:
              - status: 201
              - body.id: { exists: true }
              - body.name: { equals: "test-widget" }

        - GetWidget:
            Method: GET
            URLPath: /v1/widgets/123
            Headers:
              X-Trace-Id: { $pattern: "${hex:16}" }   # fresh hex per request
            Expect:
              - status: 200
              - body.id: { equals: { $pattern: "${captured:widgetId}" } }
              - body.name: { equals: { $pattern: "${captured:widgetName}" } }
              - body.status: { type: string }
              - duration_ms: { lt: 3000 }

        - DeleteWidget:
            Method: DELETE
            URLPath: /v1/widgets/123
            Retry: Null
            Expect:
              - status: { in: [200, 204] }

    - Name: HealthChecks
      Type: Concurrent
      ConcurrencyLimit: 3
      Requests:

        - CheckAPI:
            Method: GET
            URLPath: /health
            Expect:
              - status: 200
              - body.status: { equals: "ok" }

        - CheckDB:
            Method: GET
            URLPath: /health/db
            Expect:
              - status: 200

        - CheckCache:
            Method: GET
            URLPath: /health/cache
            Expect:
              - status: 200
```

**Secrets file** (`secrets.env`):

```
API_TOKEN=Bearer eyJhbGciOiJSUzI1NiJ9...
```

Run it:

```bash
payloadstash run config.yml --out ./output --secrets secrets.env
```

---

## Validation Rules (errors to avoid)

- `StashConfig.Name` must be non-empty.
- `Defaults.URLRoot` must be non-empty (no trailing slash).
- `Defaults.FlowControl` with both `DelaySeconds` and `TimeoutSeconds` is required.
- `Sequence.Name` values must be unique across all sequences.
- Request keys must be unique within each sequence.
- `ConcurrencyLimit` is required when `Type: Concurrent` and must not appear when `Type: Sequential`.
- `$dynamic` requires a matching `dynamics.patterns.<name>` entry (top-level or request-level).
- `$pattern` value must be a string template.
- `${captured:KEY}` is only valid inside a `$pattern` template — not in plain strings.
- `$secrets` requires a matching key in the `--secrets` file.
- Do not write `$deferred` directly — it is an internal marker.

---

## Running with Docker (prebuilt image)

The image is published to GitHub Container Registry on every push to `main` and on version tags — no build step needed.

**Set up a shell alias** (add to `~/.bashrc` or `~/.zshrc`, then `source` it):

```bash
alias payloadstash='docker run --rm -it --pull always --platform linux/amd64 -v "$(pwd):/working" -w /working ghcr.io/ericwastaken/payloadstash:main'
```

**Usage** — paths work just like the native CLI, relative to your current working directory:

```bash
# Run
payloadstash run ./config/my-config.yml --out ./output

# Run with secrets
payloadstash run ./config/my-config.yml --out ./output --secrets ./config/my-secrets.env

# Validate only
payloadstash validate ./config/my-config.yml
```

Notes:
- Your current working directory is mounted inside the container — no special directory structure required.
- `--pull always` keeps the image current on each run.
- `--platform linux/amd64` is required on Apple Silicon.
- Replace `:main` with a version tag (e.g., `:1.0.0`) to pin to a specific release.

---

## CLI Reference

```bash
# Validate only
payloadstash validate config.yml
payloadstash validate config.yml --secrets secrets.env

# Run
payloadstash run config.yml --out ./output
payloadstash run config.yml --out ./output --secrets secrets.env
payloadstash run config.yml --out ./output --dry-run  # no HTTP calls
payloadstash run config.yml --out ./output --yes      # skip confirmation prompt
```

**Exit codes:**
- `0` — run completed, all Expect assertions passed
- `1` — one or more `Expect` assertions failed
- `9` — validation error or output write error

**Run artifacts** (written to `<out>/<Name>/<timestamp>/`):
- `<config>-resolved.yml` — effective config after Defaults/Forced merge
- `<config>-run.log` — full request/response log with assertion results
- `<config>-results.csv` — one row per request: sequence, request, timestamp, status, duration_ms, attempts, expect_passed, expect_failed
- `<config>-report.md` — markdown report with assertions summary table and per-request details
- `seq<NNN>-<Name>/req<NNN>-<Key>-response.<ext>` — raw response body per request

---

## Minimal Working Example

```yaml
StashConfig:
  Name: HealthCheck
  Defaults:
    URLRoot: https://api.example.com
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10
  Sequences:
    - Name: Check
      Type: Sequential
      Requests:
        - Health:
            Method: GET
            URLPath: /health
            Expect:
              - status: 200
```

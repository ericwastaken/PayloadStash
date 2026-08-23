---
name: payloadstash
description: Create, edit, and validate PayloadStash HTTP and AMQP test suites, install or run PayloadStash, and assist maintainers with its GitHub Release and GHCR publication workflow.
---

# Use and Maintain PayloadStash

Use this skill when asked to create, edit, or extend a PayloadStash YAML config file.

Also use its maintainer section when asked to prepare, inspect, publish, troubleshoot, or clean up a PayloadStash release or GHCR package.

---

## What PayloadStash Does

PayloadStash reads a YAML config, executes HTTP requests **and/or AMQP (RabbitMQ) publishes** (sequentially or concurrently), writes each response to disk, and optionally asserts on the result. HTTP and AMQP requests can be mixed freely in the same config, and captured values flow across both. Every run produces a resolved config, a run log, a results CSV, and a markdown report.

---

## Install PayloadStash for Agent-Driven Work

Do not reinstall PayloadStash when a usable command already exists. Before installing, inspect the current project and try the matching command:

1. `payloadstash --help` for an existing UV tool or other command on `PATH`.
2. `./payloadstash --help` when the current directory is a PayloadStash release archive or bootstrap-managed checkout.
3. `uv run payloadstash --help` when the current directory is a cloned PayloadStash repository with `pyproject.toml`.

Use the command that succeeds for subsequent `validate` and `run` operations. Do not modify the environment merely to replace a working installation.

### Recommended fresh installation for an agent

When no installation exists and the user permits installing tools, prefer a **release-pinned GitHub install managed by UV**. It is isolated, non-interactive, available outside a PayloadStash checkout, easy to remove, and reproducible. PayloadStash is not published to PyPI, so the Git URL is required.

Prerequisites are Git and [UV](https://docs.astral.sh/uv/getting-started/installation/). Install the latest reviewed release tag shown by the [PayloadStash Releases page](https://github.com/ericwastaken/PayloadStash/releases/latest); for example:

```bash
uv tool install 'git+https://github.com/ericwastaken/PayloadStash.git@v1.2.0'
payloadstash --help
```

Do not silently substitute `main` when stable or reproducible behavior is expected. If the requested configuration depends on an unreleased feature, explain that tradeoff before installing the branch head:

```bash
uv tool install git+https://github.com/ericwastaken/PayloadStash.git
payloadstash --help
```

If UV reports that its tool directory is not on `PATH`, run `uv tool update-shell` and use the updated shell environment before retrying. Never claim that `uv tool install payloadstash` installs this project from PyPI.

### Validate, update, or remove the tool

After installation, verify both the executable and the configuration before attempting a run:

```bash
payloadstash --help
payloadstash validate ./config.yml
payloadstash validate ./config.yml --writeResolved
```

Reinstall with `--force` to move an existing UV tool to a chosen release tag, and uninstall it only when the user requests removal:

```bash
uv tool install --force 'git+https://github.com/ericwastaken/PayloadStash.git@v1.2.0'
uv tool uninstall payloadstash
```

### Fallback when UV is unavailable

Use the stable [GitHub Release archive](https://github.com/ericwastaken/PayloadStash/releases/latest) when Git or UV is unavailable but Python 3.8 or newer is present. Download and extract **Source code (zip)**, then run these commands from the extracted directory:

```bash
python3 bootstrap.py
./payloadstash --help
./payloadstash validate ./config.yml
```

The bootstrap creates a private `.venv` inside the extracted directory. Keep user configuration and output outside that directory so replacing or deleting the release does not remove user data. For container-only environments, follow the [GHCR Docker guide](https://ericwastaken.github.io/PayloadStash/install/docker/) instead of changing the host Python environment.

---

## Maintainer Release and GHCR Workflow

When asked for release help from a repository checkout, read `DEVELOPMENT.md`, `.github/workflows/docker-publish.yml`, and `x-payloadstash-version-set.sh` before acting. The maintained guide is also available at [DEVELOPMENT.md on GitHub](https://github.com/ericwastaken/PayloadStash/blob/main/DEVELOPMENT.md).

Release invariants:

- Update project files with `./x-payloadstash-version-set.sh 1.3.0`; do not pass the `v` prefix to the script.
- Run the four repository test scripts and any documentation checks relevant to the release.
- Commit and push the version bump to `main` before creating the release tag.
- Create tag `v1.3.0` against that exact commit, then publish the GitHub Release. A draft release does not trigger publication.
- A stable release publishes `1.3.0`, `1.3`, and `latest`. A prerelease such as `v1.4.0-rc.1` publishes only `1.4.0-rc.1`.
- Normal commits to `main` do not publish a container. Future releases do not create `main` or `sha-*` tags.
- The workflow validates version agreement, main-branch ancestry, tests, a `linux/amd64` candidate build, and the container version before authenticating to GHCR.

Before any GitHub mutation in a multi-account environment, verify the account explicitly:

```bash
gh auth switch --hostname github.com --user ericwastaken
gh api --hostname github.com user --jq .login
git remote get-url origin
```

Use `github.com` for GitHub CLI API operations even when Git uses a local SSH alias such as `github-eric.com`. Never print an authentication token.

An agent may inspect readiness, update local version files, run tests, and prepare release notes when asked. Creating or publishing a release, changing a tag, publishing an image, or deleting GHCR package versions requires explicit user authorization for that external action.

For GHCR cleanup, preserve every semantic release version and the untagged platform or provenance manifests referenced by its image index. Do not delete a version carrying a semantic release tag merely because it also has a `sha-*` alias.

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
  URLRoot: https://api.example.com   # uncovered HTTP; supports $secrets/$dynamic/$pattern/$timestamp/$func
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
          URLPath: /v1/thing  # appended to URLRoot; supports operators incl. ${captured:KEY}
          URLRoot: ...        # optional; overrides Defaults.URLRoot for this request only
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

**Transport:**
- Requests default to HTTP. To publish an AMQP message instead, set `Transport: amqp` on the request and give it an `AMQP` block (no `Method`/`URLPath`). HTTP and AMQP requests can be mixed in one sequence. See **AMQP (sending messages)** below.

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
| `headers.<name>` | Response header value (name matched case-insensitively) |
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

### JSONPath in the assertion path

The key (left side) of an assertion is a response path. Besides the simple prefixes above (`status`, `duration_ms`, `headers.<name>`, `body`, `body.<field>`, `body[N].<field>`), **a key beginning with `$` is evaluated as a JSONPath expression** against the parsed body — the same resolver `Capture` uses, including filter predicates, wildcards, and `::` aggregation suffixes. Quote the key so YAML treats it as a string.

```yaml
Expect:
  - "$.items[?(@.id=='DYX')].value": { equals: 42 }    # filter predicate → scalar
  - "$.players[*].score::sum": { gt: 100 }              # aggregate, then compare
  - "$.items[*]::count": { equals: 3 }                  # count of matches
  - "$.items[*].id": { contains: "abc" }                # wildcard → list, membership
  - "$.items[*].id": { lengthGte: 1 }                   # wildcard → list, length
  - "$.user.email": { matches: "@example\\.com$" }
```

Without an aggregation suffix a single JSONPath match yields a scalar and multiple matches yield a list — pick matchers accordingly (`contains`/`lengthEquals` for lists; `equals`/`type` for scalars). JSONPath keys apply to the parsed JSON response body — HTTP responses, and AMQP `WaitFor` reply/matched bodies (`Mode: rpc`/`subscribe`). A plain AMQP publish has no body, so assert on `status`/`headers.*`/`duration_ms` there.

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

## AMQP (sending messages)

Set `Transport: amqp` on a request to publish a message to RabbitMQ instead of making an HTTP call. Everything else you know still applies: `Body` is the message payload, `Defaults`/`Forced` merge, `dynamics`, `$secrets`, `$pattern`, `${captured:KEY}`, `Capture`, and `Expect` all work the same way. HTTP and AMQP requests can be freely mixed in one config.

```yaml
Defaults:
  URLRoot: https://api.example.com        # only needed if the config also has HTTP requests
  FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }   # TimeoutSeconds is reused as the confirm deadline
  AMQP:
    URI: "{ $secrets: RMQ_URI }"          # broker connection, e.g. amqp://user:pass@host:5672/%2F
    Confirm: true                          # publisher confirms by default

Sequences:
  - Name: publish
    Type: Sequential
    Requests:
      - emit-coin:
          Transport: amqp                  # <-- selects the AMQP transport (default is http)
          AMQP:
            Exchange: frontline.exchange
            RoutingKey: device.signal.coin
            Properties:
              DeliveryMode: persistent      # transient | persistent
              CorrelationId: { $pattern: "${uuidv4}" }
              Headers: { x-source: payloadstash }   # AMQP message (application) headers
          Body:
            bandId: { $pattern: "${hex:16}" }
            action: coin_grant
          Expect:
            - status: ack                   # AMQP status is a string, not a number
```

### The `AMQP` block

| Field | Meaning |
|---|---|
| `URI` | Broker connection string (`amqp://…` or `amqps://…`). Usually set in `Defaults.AMQP`. Supports `{ $secrets: KEY }`. |
| `Exchange` | Exchange to publish to. `""` = the default (nameless) exchange. |
| `RoutingKey` | Routing key. For the default exchange this is the queue name; for topic/direct it's matched against bindings; for fanout it's ignored. |
| `Confirm` | `true` = wait for a publisher confirm (broker ack). |
| `Mandatory` | `true` = fail if the message can't be routed to any queue. |
| `TLS` | TLS settings for `amqps://` — see below. |
| `Properties` | AMQP message properties (see below). |

At least one of `Exchange` or `RoutingKey` must be non-empty. Exchange type is broker-side: for a **fanout** exchange set only `Exchange` (routing key is ignored); to publish straight to a **queue** use `Exchange: ""` with `RoutingKey: <queue-name>`.

**`Properties`** (all optional): `ContentType`, `ContentEncoding`, `DeliveryMode` (`transient`|`persistent`), `Priority` (0–9), `CorrelationId`, `ReplyTo`, `Expiration`, `MessageId`, `Type`, `AppId`, and `Headers` (a map of AMQP application headers). A JSON `ContentType` is applied automatically when a `Body` is present and none is given.

### Result status (a string, not a number)

An AMQP publish reports a **string** `status` you assert on with `Expect`:

| `status` | When |
|---|---|
| `ack` | `Confirm: true` and the broker acknowledged |
| `nack` | `Confirm: true` and the broker rejected |
| `unroutable` | `Mandatory: true` and no queue was bound to route it |
| `published` | fire-and-forget (no `Confirm`), handed to the broker |
| `reply` | `WaitFor: { Mode: rpc }` — a correlated reply arrived (reply body available) |
| `matched` | `WaitFor: { Mode: subscribe }` — a message satisfying `Match` arrived (body available) |
| `timeout` | `WaitFor` deadline elapsed with no reply/match |

It also synthesizes response headers you can capture/assert on: `x-amqp-exchange`, `x-amqp-routing-key`, `x-amqp-confirmed`, `x-amqp-routed`.

```yaml
Expect:
  - status: ack
  - headers.x-amqp-routing-key: { equals: device.signal.coin }
  - duration_ms: { lt: 2000 }
```

### TLS / `amqps` with CA certificates

For a TLS broker use an `amqps://` URI; for a private CA add an `AMQP.TLS` block:

```yaml
Defaults:
  AMQP:
    URI: "{ $secrets: RMQ_URI }"          # amqps://user:pass@broker:5671/%2F
    TLS:
      CAFile: /etc/ssl/rabbit-ca.pem       # CA cert(s) that signed the broker cert
      # CAPath: /etc/ssl/certs             # or a directory of CA certs
      # CertFile: /etc/ssl/client.pem      # client cert for mutual TLS (optional)
      # KeyFile:  /etc/ssl/client.key      # client key for mutual TLS (optional)
      VerifyPeer: true                     # default true; verify broker cert + hostname
      # ServerName: rabbit.internal        # override the hostname verified via SNI
```

- TLS is applied only for `amqps://` URIs.
- `CAFile`/`CAPath` replace the default trust store — point `CAFile` at a bundle if you also need the system CAs.
- `VerifyPeer: false` disables certificate and hostname checking (test only).

### Awaiting a response: RPC and WaitFor

Add a `WaitFor` block to **publish, then wait for a response message** — one operation, with a timeout. Two modes:

**`Mode: rpc`** — await a correlated reply on an auto-generated reply queue (PayloadStash sets `reply_to` + `correlation_id` on your message). The reply body becomes the response body, so `Capture`/`Expect`/`$jsonpath` work on it. Status is `reply` or `timeout`.

```yaml
- resolve-band:
    Transport: amqp
    AMQP:
      Exchange: ""
      RoutingKey: rpc.resolve
      WaitFor: { Mode: rpc, TimeoutSeconds: 5 }   # TimeoutSeconds optional (defaults to FlowControl)
    Body: { bandId: "04AABBCC" }
    Capture:
      playFabId: { $jsonpath: "$.result.PlayFabId" }   # captured from the reply
    Expect:
      - status: reply
      - "$.result.PlayFabId": { type: string }
```

**`Mode: subscribe`** — bind a temporary queue to an exchange *before* publishing, then publish a trigger and wait for a message satisfying `Match`. Use this to assert on a **downstream broadcast/side-effect** (e.g. a fanout state update) that isn't a direct reply. Status is `matched` or `timeout`.

```yaml
- signal-and-await-broadcast:
    Transport: amqp
    AMQP:
      Exchange: frontline.exchange          # where the trigger goes
      RoutingKey: device.signal.coin
      WaitFor:
        Mode: subscribe
        Exchange: state.fanout              # temp queue is bound here, BEFORE publishing
        RoutingKey: ""                       # binding key (ignored by fanout)
        TimeoutSeconds: 5
        Match:                               # Expect-style list; the awaited message must satisfy ALL
          - "$.event": { equals: state_update }
          - "$.playFabId": { equals: { $pattern: "${captured:playFabId}" } }
    Body: { playFabId: { $pattern: "${captured:playFabId}" }, action: coin_grant }
    Expect:
      - status: matched
```

Notes:
- `Match` uses the same matchers as `Expect`, evaluated against each received message's body (`$.`/`body.*`) and headers (`headers.*`, including `headers.x-amqp-routing-key`). The first message satisfying all conditions wins; others are discarded (`headers.x-amqp-nonmatching-count` reports how many were skipped).
- For `subscribe` the listener is established *before* the trigger is published, so a fast broadcast can't be missed.
- `rpc` forbids `Exchange`/`RoutingKey`/`Match` under `WaitFor`; `subscribe` requires `Exchange` + `Match`.
- The reply/matched message's body feeds `Capture`, so `${captured:KEY}` can carry it into later requests.
- `duration_ms` for a WaitFor request includes the time spent awaiting. The await portion is also broken out as an `x-amqp-wait-ms` response header (shown as `(awaited Nms)` next to Duration in the report, and assertable via `headers.x-amqp-wait-ms`).

### Fanout broadcast + mixed HTTP/AMQP

```yaml
Sequences:
  - Name: signal-then-verify
    Type: Sequential
    Requests:
      - broadcast:                          # fanout: routing key omitted (ignored anyway)
          Transport: amqp
          AMQP: { Exchange: state.fanout }
          Body: { type: ping }
          Expect: [ { status: ack } ]

      - verify-http:                        # HTTP request in the same sequence
          Method: GET
          URLPath: /health
          Expect: [ { status: 200 } ]
```

**`Defaults`/`Forced` for AMQP:** the `AMQP` block merges like `Headers` (request over Defaults, Forced last; `Properties.Headers` is deep-merged). HTTP-only sections (`URLRoot`, `Headers`, `Query`, `InsecureTLS`, `Response`) do not apply to AMQP requests; `Body`, `Retry`, and `FlowControl` are shared. `Defaults.URLRoot` is required only when the config contains an HTTP request without its own request-level `URLRoot`. `Retry` on an AMQP request retries connection/network errors only — a `nack`/`unroutable` is a broker decision, not retried.

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

### Use a different URL root per request

Set `URLRoot` directly on an HTTP request to override `Defaults.URLRoot` for that request. If every HTTP request supplies its own root, `Defaults.URLRoot` may be omitted. The override also accepts the same value operators as the default root.

```yaml
StashConfig:
  Name: MultiServiceHealth
  Defaults:
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
  Sequences:
    - Name: CheckServices
      Type: Sequential
      Requests:
        - CheckAccounts:
            Method: GET
            URLRoot: https://accounts.example.com
            URLPath: /health
        - CheckOrders:
            Method: GET
            URLRoot: { $secrets: ORDERS_URL_ROOT }
            URLPath: /health
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

## Full Working Example — AMQP

A realistic AMQP config: broker URI + TLS/CA from secrets, an anchor for shared message properties, a dynamic band id, publisher confirms, a topic publish, a fanout broadcast, a concurrent burst, and an HTTP health check in the same run (transports mix freely).

```yaml
# Reusable AMQP message properties
common_props: &common_props
  DeliveryMode: persistent
  Headers:
    x-source: payloadstash

dynamics:
  patterns:
    bandId:
      template: "04${hex:14}"                   # NFC band id, fresh per request

StashConfig:
  Name: SnwDeviceSignals

  Defaults:
    URLRoot: https://api.snw.example.com        # only used by the HTTP verify step
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10                         # doubles as the publish/confirm deadline
    AMQP:
      URI: "{ $secrets: RMQ_URI }"              # amqps://user:pass@gam02:5671/%2F
      Confirm: true                              # ack/nack on every publish
      Exchange: frontline.exchange               # default target exchange for these publishes
      TLS:
        CAFile: /etc/ssl/certs/rabbit-ca.pem     # broker CA bundle (amqps)
        VerifyPeer: true

  Forced:
    AMQP:
      Properties:
        Headers:
          x-run: smoke                           # tags every message; deep-merged with per-request headers

  Sequences:

    - Name: EmitSignals
      Type: Sequential
      Requests:

        - emit-coin:                             # topic publish, confirmed
            Transport: amqp
            AMQP:
              RoutingKey: device.signal.coin
              Properties:
                <<: *common_props
                CorrelationId: { $pattern: "${uuidv4}" }
            Body:
              bandId: { $dynamic: bandId, when: request }
              action: coin_grant
              ts: { $timestamp: { format: epoch_ms, when: request } }
            Expect:
              - status: ack
              - headers.x-amqp-routing-key: { equals: device.signal.coin }

        - broadcast-refresh:                     # fanout: routing key omitted (ignored)
            Transport: amqp
            AMQP: { Exchange: state.fanout }
            Body: { type: refresh }
            Expect:
              - status: ack

    - Name: BurstBananas                         # publish several messages concurrently
      Type: Concurrent
      ConcurrencyLimit: 4
      Requests:
        - b1: { Transport: amqp, AMQP: { RoutingKey: device.signal.banana }, Body: { action: banana_grant } }
        - b2: { Transport: amqp, AMQP: { RoutingKey: device.signal.banana }, Body: { action: banana_grant } }
        - b3: { Transport: amqp, AMQP: { RoutingKey: device.signal.banana }, Body: { action: banana_grant } }

    - Name: VerifyOverHttp                       # an HTTP request in the same run
      Type: Sequential
      Requests:
        - health:
            Method: GET
            URLPath: /health
            Expect:
              - status: 200
```

**Secrets file** (`secrets.env`):

```
RMQ_URI=amqps://guest:guest@gam02.park.internal:5671/%2F
```

Run it:

```bash
payloadstash run amqp-signals.yml --out ./output --secrets secrets.env
```

---

## Validation Rules (errors to avoid)

- `StashConfig.Name` must be non-empty.
- `Defaults.URLRoot` must be non-empty when the config has HTTP requests that do not define their own request-level `URLRoot`; it may be omitted for AMQP-only configs or when every HTTP request carries its own `URLRoot`. It may be a plain string or a `$secrets`/`$dynamic`/`$pattern`/`$timestamp`/`$func: timestamp` operator (same as `URLPath`). An HTTP request may set a non-null `URLRoot` to override `Defaults.URLRoot` for that request only; omission inherits the default.
- `Defaults.FlowControl` with both `DelaySeconds` and `TimeoutSeconds` is required.
- `Sequence.Name` values must be unique across all sequences.
- Request keys must be unique within each sequence.
- `ConcurrencyLimit` is required when `Type: Concurrent` and must not appear when `Type: Sequential`.
- `$dynamic` requires a matching `dynamics.patterns.<name>` entry (top-level or request-level).
- `$pattern` value must be a string template.
- `${captured:KEY}` is only valid inside a `$pattern` template — not in plain strings.
- `$secrets` requires a matching key in the `--secrets` file.
- Do not write `$deferred` directly — it is an internal marker.
- `Transport: amqp` requires an `AMQP` block; HTTP-only keys (`Method`, `URLPath`, `Query`, `URLRoot`, `InsecureTLS`, `Response`, `Headers`) are not allowed on an AMQP request, and an `AMQP` block is not allowed on an HTTP request.
- Every AMQP request needs a resolvable broker URI (`AMQP.URI` on the request or in `Defaults.AMQP`) and at least one of `AMQP.Exchange` / `AMQP.RoutingKey` non-empty.

---

## Running with Docker (prebuilt image)

The image is published to GitHub Container Registry only when a GitHub Release is published. Normal commits to `main` do not publish images.

**Set up a shell alias** (add to `~/.bashrc` or `~/.zshrc`, then `source` it):

```bash
alias payloadstash='docker run --rm -it --pull always --platform linux/amd64 -v "$(pwd):/working" -w /working ghcr.io/ericwastaken/payloadstash:latest'
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
- `:latest` follows the newest stable release. Replace it with a version tag such as `:1.2.0` to pin to a reproducible release.

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
- `<config>-results.csv` — one row per request: sequence, request, timestamp, status, duration_ms, attempts, expect_passed, expect_failed (status is the HTTP code for HTTP requests, or a label like `ack`/`nack` for AMQP)
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

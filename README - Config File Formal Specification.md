# README - Config File Formal Specification

- Version: 1.1  
- Last updated: 2026-05-13

## Scope
- This document formally defines the PayloadStash YAML configuration syntax and resolution rules so that an IDE or LLM 
  can implement authoring, validation, and transformation tools.
- The configuration files are UTF-8 encoded YAML 1.2 documents.

## High‑level overview
- A config file is a YAML mapping with the required key `StashConfig` and an optional key `dynamics`.
- All other top-level keys are allowed (e.g., YAML anchors) and ignored by the parser, but are not part of the formal model.
- Short mapping forms for special `$` operators are preferred and should be encouraged by tooling.
  - Example (preferred): `artifactId: { $dynamic: artifactid }`

## Top-level structure
TopLevelConfig (YAML mapping)
- `StashConfig`: StashConfig (required)
- `dynamics`: Dynamics (optional)
- Additional keys: allowed (ignored by model)

## Dynamics
Dynamics (mapping, extra keys forbidden)
- `patterns`: map<string, DynamicPattern> (required)
- `sets`: map<string, list<string>> (optional)

### DynamicPattern
- `template`: string (required)

## StashConfig
StashConfig (mapping, extra keys forbidden)
- `Name`: string (required, non-empty)
- `Defaults`: DefaultsSection (required)
- `Forced`: ForcedSection (optional)
- `Sequences`: list<Sequence> (required, non-empty)

## Validation rules
- `StashConfig.Defaults.URLRoot`: non-empty string, required.
- `StashConfig.Defaults.FlowControl`: required and must include `DelaySeconds` (int>=0) and `TimeoutSeconds` (int>=0). 
  Values validated individually; presence required.
- `Sequence.Name` values must be unique across the config.
- Within each `Sequence`, Request keys must be unique.
- For `Sequence.Type`:
  - If `Type == "Concurrent"`: `ConcurrencyLimit` is required and must be int>=1.
  - If `Type == "Sequential"`: `ConcurrencyLimit` must not be present.
- `Capture` path strings must use one of the supported prefixes: `status`, `duration_ms`, `headers.<name>`, `body`, `body.<field>`, `body[N].<field>`. Invalid prefixes are rejected at config-load time.
- `$pattern` requires a non-empty string template value. Template syntax (placeholder forms) is validated at config-load time.

## Section types

### DefaultsSection (mapping, extra keys forbidden)
- `URLRoot`: string (required, non-empty)
- `FlowControl`: FlowControlCfg (required)
- `InsecureTLS`: bool (optional; default false). When true, TLS certificate verification and hostname checks are 
  disabled for requests (similar to curl --insecure).
- `Headers`: map<string, any> (optional)
- `Body`: map<string, any> (optional)
- `Query`: map<string, any> (optional)
- `Retry`: Retry (optional) [internal alias `RetryCfg`]
- `Response`: ResponseCfg (optional)

### ForcedSection (mapping, extra keys forbidden)
- `Headers`: map<string, any> (optional)
- `Body`: map<string, any> (optional)
- `Query`: map<string, any> (optional)
- `Retry`: Retry (optional) [internal alias `RetryCfg`]

### FlowControlCfg (mapping, extra keys forbidden)
- `DelaySeconds`: int>=0 (optional depending on context; required in `Defaults.FlowControl`)
- `TimeoutSeconds`: int>=0 (optional depending on context; required in `Defaults.FlowControl`)

### Retry (mapping, extra keys forbidden; enums serialized as values)
- `Attempts`: int>=1 (required)
- `BackoffStrategy`: enum { `fixed`, `exponential` } (required)
- `BackoffSeconds`: float>=0 (required)
- `Multiplier`: float>0 (optional)
- `MaxBackoffSeconds`: float>=0 (optional)
- `MaxElapsedSeconds`: float>=0 (optional)
- `Jitter`: bool | string (optional; if string, one of: "min", "max")
- `RetryOnStatus`: list<int> (optional)
- `RetryOnNetworkErrors`: bool (optional)
- `RetryOnTimeouts`: bool (optional)

Note: Retry may be explicitly set to null (YAML `null`/`Null`) at any level to disable retries at that level; explicit 
null is preserved and overrides lower-precedence Retry.

## Sequences and Requests

### Sequence (mapping, extra keys forbidden)
- `Name`: string (required)
- `Type`: enum { `Sequential`, `Concurrent` } (required)
- `ConcurrencyLimit`: int>=1 (required iff `Type==Concurrent`; forbidden iff `Type==Sequential`)
- `Requests`: list<RequestItem> (required, non-empty)

### RequestItem (one-of mapping form; exactly one key)
- Form: `{ <RequestKey>: Request }`
- `<RequestKey>`: string, unique within the sequence

### Request (mapping, extra keys forbidden)
- `Method`: enum { `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` } (required)
- `URLPath`: string (required)
- `Headers`: map<string, any> (optional)
- `Body`: map<string, any> (optional)
- `Query`: map<string, any> (optional)
- `FlowControl`: FlowControlCfg (optional)
- `Retry`: Retry (optional) [internal alias `RetryCfg`]
- `Response`: ResponseCfg (optional)
- `InsecureTLS`: bool (optional) — overrides `Defaults.InsecureTLS` when provided.
- `Capture`: map<string, string> (optional) — extracts values from the response into the run-level captured dict. See `## Capture`.
- `Expect`: list<map<string, any>> (optional) — assertions evaluated after the response. See `## Expect`.
- `dynamics`: Dynamics (optional) — request-level dynamics merged with (and overriding) the top-level `dynamics` section.

### ResponseCfg (mapping, extra keys forbidden)
- `PrettyPrint`: bool (optional) — if true, pretty-prints supported response types when writing files.
- `Sort`: bool (optional) — if true, sorts the response; implies PrettyPrint. For JSON, sorts object keys; for XML, 
  sorts element children by tag name and attributes alphabetically. Other content types ignored.

## Capture

A `Capture` block on a Request extracts values from the HTTP response and stores them in the run-level `captured` dict. Captured values persist for the lifetime of the run and are accessible to all subsequent requests via `$pattern` templates using the `${captured:KEY}` placeholder.

Schema:
- `Capture`: map<string, string>
  - Key: capture variable name (string, non-empty)
  - Value: response path string (see supported prefixes below)

Supported path prefixes:
- `status` → HTTP status code (int)
- `duration_ms` → request duration in milliseconds (int)
- `headers.<name>` → response header value; `<name>` must be lowercase
- `body` → entire parsed response body
- `body.<field>` → dot-notation path into parsed JSON body
- `body[N].<field>` → array index `N` into parsed JSON body, then dot-notation field

Example:
```yaml
Capture:
  thingId: body.id
  elapsed: duration_ms
  serverTime: headers.x-timestamp
```

Notes:
- Capture runs after the response is received and after `Expect` assertions are evaluated.
- If a path does not resolve (e.g., field missing), the captured value is `null`.
- Captured values are available only in `$pattern` templates via `${captured:KEY}`.

## Expect

An `Expect` list on a Request defines assertions evaluated against the response. All assertions run (no short-circuit). If any assertion fails, the run exits with code 1 after the run completes.

Schema:
- `Expect`: list<map<string, matcher>>
  - Each item in the list is a single-key map: `{ <path>: <matcher> }`
  - `path`: response path string — same resolution prefixes as `Capture` (`status`, `duration_ms`, `headers.<name>`, `body`, `body.<field>`, `body[N].<field>`)
  - `matcher`: a primitive value (shorthand for `equals`) OR a map of matcher key → value

Matcher reference:
- `equals` / `notEquals` — deep equality check
- `exists: bool` — `true` = value is not null/missing; `false` = value is null/missing
- `type: string` — asserts JSON type; one of: `string`, `number`, `integer`, `boolean`, `object`, `array`, `null`
- `matches` / `notMatches` — regex pattern applied to the stringified value
- `contains` / `notContains` — substring check for strings; element membership check for arrays
- `in` / `notIn` — asserts the value is/is not a member of a provided list
- `lengthEquals` / `lengthGte` / `lengthLte` — length assertion for arrays or strings
- `gt` / `gte` / `lt` / `lte` — numeric comparison

Shorthand: a primitive value is sugar for `{ equals: <value> }`.
- `status: 200` is equivalent to `status: { equals: 200 }`

`$pattern` references are valid inside matcher values:
```yaml
Expect:
  - body.id: { equals: { $pattern: "${captured:thingId}" } }
```

Example:
```yaml
Expect:
  - status: 201
  - body.id: { exists: true }
  - body.name: { type: string }
  - body.tags: { contains: "active" }
  - duration_ms: { lte: 2000 }
```

## Value resolution model
The runner builds a resolved request set from the authored config using these rules:

1) Section merge for Headers/Body/Query (per request)
   - Start with the request-level section if provided; else use `Defaults.<Section>` if provided; else null.
   - Overlay `Forced.<Section>` last (keys in Forced overwrite earlier ones).
   - After merges, resolve special operators (`$dynamic`, `$secrets`, `$timestamp`/`$func`, `$pattern`) recursively within the merged maps.

2) Retry precedence with explicit-null awareness
   - Precedence: `request.Retry` (even if null) > `Defaults.Retry` (even if null).
   - Only fall through when a level omits the `Retry` field entirely.
   - In the resolved output, `Retry` appears under each request if set by precedence. Explicit null is preserved.

3) URLRoot propagation
   - Each resolved request includes `URLRoot` copied from `Defaults.URLRoot`.

4) FlowControl overlay
   - Effective `FlowControl` results from `Defaults.FlowControl` overlaid by `request.FlowControl` field-wise (`DelaySeconds`, `TimeoutSeconds`).

5) Dynamics precomputation
   - At resolve-time, for non-deferred `$dynamic` entries, each named pattern is computed once per file and reused for 
     that name to ensure consistency.
   - Request-level `dynamics` are merged with the top-level `dynamics` before precomputation; request-level keys win on conflict.

6) `$pattern` always defers
   - `$pattern` operators are always treated as request-time deferred regardless of context. No `when` field is needed.
   - The template syntax is validated at config-load time, but expansion occurs at request time so runtime values (including captured values) are available.

7) Capture and Expect run at request time
   - After the HTTP response is received, `Expect` assertions are evaluated first.
   - Then `Capture` paths are resolved and stored in the run-level `captured` dict.
   - Captured values from earlier requests are available to later requests via `${captured:KEY}` inside `$pattern` templates.

## Special operators ($...)
Tooling should prefer and generate the concise mapping forms for all special operators. Long/verbose forms are allowed 
when specified but should be discouraged.

### 1) `$dynamic` — dynamic value from named pattern
- Preferred form (mapping value):
  ```yaml
  key: { $dynamic: patternName }
  ```
- Optional deferral to request time:
  ```yaml
  key: { $dynamic: patternName, when: request }
  ```
- Default `when` is `resolve`.
- Behavior:
  - Requires a top-level `dynamics` section with `patterns[patternName].template` (string) and optional `sets`.
  - When `when: resolve` (default): the template is expanded immediately at resolve time.
  - When `when: request`: validation checks the template, and a deferred marker is stored; the actual value is produced 
    later at request time.
- Errors:
  - Missing `dynamics` section when `$dynamic` is used.
  - Unknown `patternName`.
  - Non-string `patternName`.

### 2) `$secrets` — secret value lookup
- Preferred mapping form:
  ```yaml
  key: { $secrets: SECRET_KEY }
  ```
- Supported inline string interpolation form:
  ```yaml
  key: "prefix { $secrets: SECRET_KEY } suffix"
  ```
- Behavior:
  - Requires a secrets map provided externally (e.g., via `--secrets` file). If redact mode is on, resolved values are 
    replaced by `***REDACTED***` in resolved output.
- Errors:
  - Secrets map not provided when required.
  - `SECRET_KEY` not present in provided secrets map.

### 3) `$timestamp` / `$func: timestamp` — generated timestamp
- Shorthand form:
  ```yaml
  key: { $timestamp: format }
  ```
  where `format` is one of: `iso_8601` (default), `epoch_ms`, or other formats supported by the runner.
- Long form (discouraged, but supported):
  ```yaml
  key: { $func: timestamp, format: format }
  ```
- Optional deferral:
  ```yaml
  key: { $timestamp: { format: epoch_ms, when: request } }
  ```
  or
  ```yaml
  key: { $func: timestamp, format: epoch_ms, when: request }
  ```
- Behavior:
  - When `when: resolve` (default): the timestamp value is generated immediately.
  - When `when: request`: a deferred marker is placed; actual value is computed at request time.

### 4) `$pattern` — inline request-time template
- Form:
  ```yaml
  key: { $pattern: "template string" }
  ```
- Behavior:
  - Always defers to request time. No `when` field is required or supported.
  - The template string supports all the same placeholders as `dynamics.patterns.template` (see `## Dynamic template language`), including `${captured:KEY}` to reference values stored by a `Capture` block.
  - Validated at config-load time (template syntax checked); expanded at request time.
  - `$deferred` marker produced: `{"$deferred": {"pattern": {"template": "...", "sets": {...}}}}`
- Errors:
  - Non-string template value.
  - Invalid placeholder syntax in template (detected at config-load time).

Examples:
```yaml
Body:
  traceId: { $pattern: "${hex:16}" }
  parentId: { $pattern: "${captured:thingId}" }
  env: { $pattern: "${choice:envs}" }
```

### Notes on `$deferred`
- `$deferred` nodes are internal artifacts produced when `when: request` is specified or when `$pattern` is used. Authors should not write `$deferred` directly.

## Examples (authoring) — concise forms

Dynamic value (preferred):
```yaml
Body:
  artifactId: { $dynamic: artifactid }
  universalId: { $dynamic: universalid }
```

Secret in header (preferred mapping form):
```yaml
Headers:
  Authorization: { $secrets: api_token }
```

Secret inline interpolation (also supported):
```yaml
Headers:
  Authorization: "Bearer { $secrets: api_token }"
```

Timestamp (shorthand):
```yaml
Query:
  ts: { $timestamp: epoch_ms }
```

Deferred generation at request time:
```yaml
Body:
  requestTs: { $timestamp: { format: epoch_ms, when: request } }
```

Minimal sequence with a request:
```yaml
StashConfig:
  Name: Sample
  Defaults:
    URLRoot: https://api.example.com
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 30
  Sequences:
    - Name: example_seq
      Type: Sequential
      Requests:
        - get_thing:
            Method: GET
            URLPath: /v1/thing
            Query:
              id: { $dynamic: thing_id }
```

Dynamics example:
```yaml
dynamics:
  patterns:
    artifactid: { template: "artifact-{N}" }
    universalid: { template: "uid-{N}" }
  sets:
    N: ["001", "002", "003"]
```

## Error conditions (non-exhaustive)
- Missing top-level `StashConfig` when keys like `Defaults`/`Sequences` are present at root; the loader will raise with guidance to wrap content under `StashConfig`.
- Duplicate `Sequence.Name` values.
- Duplicate Request keys within a `Sequence`.
- Using `$dynamic` without defining `dynamics.patterns`.
- `$secrets` reference without providing a secrets map or referencing an unknown secret key.
- Invalid enum values for `Method`, `Sequence.Type`, `BackoffStrategy`.
- Invalid numeric constraints (e.g., negative `DelaySeconds`, `Attempts<1`).
- `Capture` path string with an unknown or malformed prefix.
- `$pattern` with a non-string template or invalid placeholder syntax in the template string.
- `${captured:KEY}` referenced in a context other than a `$pattern` template.

## Authoring guidance
- Prefer concise mapping forms for special operators:
  - `{ $dynamic: name }`
  - `{ $secrets: key }`
  - `{ $timestamp: format }`
  - `{ $pattern: "template string" }`
- Avoid verbose multi-line function objects unless needed for `when: request`.
- Keep Sequence and Request keys stable and descriptive; they are used for reporting outputs.
- Use `$pattern` for one-off inline templates or to reference captured values; use `$dynamic` for named reusable patterns.
- `Capture` variable names should be stable and descriptive; they are referenced by name in `${captured:KEY}` placeholders.

## Dynamic template language for `dynamics.patterns.template`
Supported placeholders inside template strings (expanded by the runner):
- `${hex:N}`               → N random hex characters (uppercase A–F)
- `${alphanumeric:N}`      → N random characters 0-9 A-Z a-z
- `${numeric:N}`           → N random digits 0-9
- `${alpha:N}`             → N random letters A-Z a-z
- `${uuidv4}`              → UUID v4 string
- `${choice:setName}`      → pick one element from `dynamics.sets[setName]`
- `${timestamp[:format]}`  → current UTC timestamp; format one of `epoch_ms` | `epoch_s` | `iso_8601` (default `iso_8601`)
- `${@timestamp[:format]}` → alias for `${timestamp[:format]}`
- `${secrets:KEY}`         → inject secret value for `KEY` from the provided secrets file
- `${captured:KEY}`        → value previously stored by a `Capture` block on an earlier request; only valid inside `$pattern` templates (not in `dynamics.patterns.template`)

Notes:
- Inline secrets are also supported in any string: "... { $secrets: KEY } ...".
- Unknown placeholders are left as-is (no expansion) to avoid data loss.
- `${captured:KEY}` resolves to `null` (empty string in string context) if the key has not been captured yet.

## Compatibility
- YAML anchors/aliases and merge keys (`<<`) are supported by the YAML loader and may appear anywhere. The model ignores 
  unknown extra keys at the top level but forbids extras within typed sections.

---

End of specification.

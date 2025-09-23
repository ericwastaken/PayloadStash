# README - Config File Formal Specification

- Version: 1.0  
- Last updated: 2025-09-23

## Scope
- This document formally defines the PayloadStash YAML configuration syntax and resolution rules so that an IDE or LLM can implement authoring, validation, and transformation tools.
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
- `Retry`: Retry (optional) [YAML key is "Retry"; internal alias `RetryCfg`]
- `Sequences`: list<Sequence> (required, non-empty)

## Validation rules
- `StashConfig.Defaults.URLRoot`: non-empty string, required.
- `StashConfig.Defaults.FlowControl`: required and must include `DelaySeconds` (int>=0) and `TimeoutSeconds` (int>=0). Values validated individually; presence required.
- `Sequence.Name` values must be unique across the config.
- Within each `Sequence`, Request keys must be unique.
- For `Sequence.Type`:
  - If `Type == "Concurrent"`: `ConcurrencyLimit` is required and must be int>=1.
  - If `Type == "Sequential"`: `ConcurrencyLimit` must not be present.

## Section types

### DefaultsSection (mapping, extra keys forbidden)
- `URLRoot`: string (required, non-empty)
- `FlowControl`: FlowControlCfg (required)
- `Headers`: map<string, any> (optional)
- `Body`: map<string, any> (optional)
- `Query`: map<string, any> (optional)
- `Retry`: Retry (optional) [internal alias `RetryCfg`]

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

Note: Retry may be explicitly set to null (YAML `null`/`Null`) at any level to disable retries at that level; explicit null is preserved and overrides lower-precedence Retry.

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

## Value resolution model
The runner builds a resolved request set from the authored config using these rules:

1) Section merge for Headers/Body/Query (per request)
   - Start with the request-level section if provided; else use `Defaults.<Section>` if provided; else null.
   - Overlay `Forced.<Section>` last (keys in Forced overwrite earlier ones).
   - After merges, resolve special operators (`$dynamic`, `$secrets`, `$timestamp`/`$func`) recursively within the merged maps.

2) Retry precedence with explicit-null awareness
   - Precedence: `request.Retry` (even if null) > `Defaults.Retry` (even if null) > `StashConfig.Retry` (even if null).
   - Only fall through when a level omits the `Retry` field entirely.
   - In the resolved output, `Retry` appears under each request if set by precedence. Explicit null is preserved.

3) URLRoot propagation
   - Each resolved request includes `URLRoot` copied from `Defaults.URLRoot`.

4) FlowControl overlay
   - Effective `FlowControl` results from `Defaults.FlowControl` overlaid by `request.FlowControl` field-wise (`DelaySeconds`, `TimeoutSeconds`).

5) Dynamics precomputation
   - At resolve-time, for non-deferred `$dynamic` entries, each named pattern is computed once per file and reused for that name to ensure consistency.

## Special operators ($...)
Tooling should prefer and generate the concise mapping forms for all special operators. Long/verbose forms are allowed when specified but should be discouraged.

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
  - When `when: request`: validation checks the template, and a deferred marker is stored; the actual value is produced later at request time.
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
  - Requires a secrets map provided externally (e.g., via `--secrets` file). If redact mode is on, resolved values are replaced by `***REDACTED***` in resolved output.
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

### Notes on `$deferred`
- `$deferred` nodes are internal artifacts produced when `when: request` is specified. Authors should not write `$deferred` directly.

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

## Authoring guidance
- Prefer concise mapping forms for special operators:
  - `{ $dynamic: name }`
  - `{ $secrets: key }`
  - `{ $timestamp: format }`
- Avoid verbose multi-line function objects unless needed for `when: request`.
- Keep Sequence and Request keys stable and descriptive; they are used for reporting outputs.

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

Notes:
- Inline secrets are also supported in any string: "... { $secrets: KEY } ...".
- Unknown placeholders are left as-is (no expansion) to avoid data loss.

## Compatibility
- YAML anchors/aliases and merge keys (`<<`) are supported by the YAML loader and may appear anywhere. The model ignores unknown extra keys at the top level but forbids extras within typed sections.

---

End of specification.

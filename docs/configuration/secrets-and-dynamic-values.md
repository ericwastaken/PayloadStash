# Secrets and dynamic values

PayloadStash operators can load protected values, generate identifiers, and delay values until a request is sent.

## Secrets

Pass a case-sensitive `KEY=VALUE` file with `--secrets`:

```dotenv
# Blank lines and comments are ignored
AUTH_TOKEN="abc123"
RMQ_URI=amqp://user:password@broker.example/%2F
```

Duplicate keys use the last value. Matching single or double quotes around an entire value are stripped.

Use either a replacement mapping or inline interpolation:

```yaml
Headers:
  X-API-Key: { $secrets: AUTH_TOKEN }
  Authorization: "Bearer { $secrets: AUTH_TOKEN }"
```

Missing files or keys fail validation. Resolved files and run logs replace loaded values with `***REDACTED***`, but service responses and captures can still contain sensitive data.

## Timestamp operators

```yaml
createdAt: { $timestamp: iso_8601 }
sentAt: { $timestamp: { format: epoch_ms, when: request } }
legacyForm: { $func: timestamp, format: epoch_s }
```

Formats are `iso_8601`, `epoch_ms`, and `epoch_s`. `when: resolve` is the default; `when: request` defers generation until sending.

## Named dynamics

Define reusable templates at the YAML top level:

```yaml
dynamics:
  patterns:
    user_id:
      template: "user-${hex:8}-${choice:regions}"
  sets:
    regions: [na, eu, ap]
```

Then use them in request values:

```yaml
Body:
  stableForRun: { $dynamic: user_id }
  freshForRequest: { $dynamic: user_id, when: request }
```

Resolve-time uses of one named pattern share its static generated value. Request-time uses generate a fresh value when sent.

## Inline patterns

`$pattern` is always evaluated at request time and does not need a named pattern:

```yaml
Body:
  requestId: { $pattern: "req-${uuidv4}" }
  previousId: { $pattern: "${captured:itemId}" }
```

| Placeholder | Result |
| --- | --- |
| `${hex:N}` | `N` random hexadecimal characters |
| `${alphanumeric:N}` | `N` letters or digits |
| `${numeric:N}` | `N` digits |
| `${alpha:N}` | `N` letters |
| `${uuidv4}` | UUID version 4 |
| `${choice:setName}` | Random item from a defined set |
| `${timestamp[:format]}` | Current UTC timestamp |
| `${secrets:KEY}` | Loaded secret value |
| `${captured:KEY}` | Value captured by an earlier request |

Use `${captured:KEY}` only inside `$pattern`; it needs a previous request and therefore cannot resolve at configuration load time.
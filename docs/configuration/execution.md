# Sequencing, concurrency, and retries

Sequences execute in listed order. Requests within each sequence run according to its `Type`.

```yaml
Sequences:
  - Name: Setup
    Type: Sequential
    Requests:
      - Prepare: { Method: POST, URLPath: /prepare }
  - Name: FetchInParallel
    Type: Concurrent
    ConcurrencyLimit: 4
    Requests:
      - FetchA: { Method: GET, URLPath: /a }
      - FetchB: { Method: GET, URLPath: /b }
```

- `Sequential` sends one request at a time and applies the effective delay after each request.
- `Concurrent` uses a worker pool. `ConcurrencyLimit` is required and must be positive; the runner never creates more workers than requests.
- One request error does not stop later requests. Add `Expect` rules when failures must make the overall command fail.

## Flow control

```yaml
Defaults:
  FlowControl:
    DelaySeconds: 1
    TimeoutSeconds: 10
```

Both values are non-negative. A request may override either field while inheriting the other. `TimeoutSeconds` applies to the operation, including AMQP publish/wait behavior where applicable.

## Retry policy

```yaml
Defaults:
  Retry:
    Attempts: 4
    BackoffStrategy: exponential
    BackoffSeconds: 0.5
    Multiplier: 2
    MaxBackoffSeconds: 10
    MaxElapsedSeconds: 30
    Jitter: true
    RetryOnStatus: [429, 500, 502, 503, 504]
    RetryOnNetworkErrors: true
    RetryOnTimeouts: true
```

`Attempts` includes the first try. `fixed` uses the base delay every time; `exponential` multiplies it for successive retries. Caps limit one delay or the total retry window. Jitter may be `false`, `true`, `min`, or `max`.

A request either inherits the default retry object, provides a complete override, or disables retries explicitly:

```yaml
Retry: null
```

For AMQP, connection/channel failures, publish failures, and wait timeouts are retried according to the effective policy; HTTP can additionally select response status codes.
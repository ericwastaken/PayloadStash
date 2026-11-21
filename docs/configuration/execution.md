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
    RetryOnExpectFailure: false
```

`Attempts` includes the first try. `fixed` uses the base delay every time; `exponential` multiplies it for successive retries. Caps limit one delay or the total retry window. Jitter may be `false`, `true`, `min`, or `max`.

A request either inherits the default retry object, provides a complete override, or disables retries explicitly:

```yaml
Retry: null
```

For AMQP, connection/channel failures, publish failures, and wait timeouts are retried according to the effective policy; HTTP can additionally select response status codes.

### Retry until expectations pass

`RetryOnExpectFailure: true` makes an HTTP request poll: a response that fails any of the request's [expectations](expectations.md) (including inherited `Defaults.Expect`) is retried like a status in `RetryOnStatus`, using the same backoff, `Attempts` and `MaxElapsedSeconds`. Each attempt is a fresh send: request-time values (`{ $timestamp: …, when: request }`, `{ $dynamic: …, when: request }`, `$pattern`, including `${captured:KEY}`) are generated again before every retry, so a `timestamp` header is never older than the backoff. Resolve-time values and captured values stay the same on every attempt, and the run log shows the first attempt's resolved request plus a `Retry: re-resolved request-time values` line per retry. Retries for `RetryOnStatus`, network errors and timeouts on a request without the flag still re-send the first attempt unchanged, as in 1.2.0. Captures and assertion results come from the final response, so running out of attempts reports the last response's failures normally. Each retry is logged with the number of failed assertions, and the CSV `attempts` column counts every attempt.

```yaml
Retry:
  Attempts: 30
  BackoffStrategy: fixed
  BackoffSeconds: 2
  MaxElapsedSeconds: 60
  RetryOnExpectFailure: true
```

Setting the flag on a request that has no expectations, or on an AMQP request, is a validation error (use `WaitFor` to await AMQP messages). Inherited from `Defaults.Retry`, it has no effect on such requests.

Set the flag on the request that polls, not in `Defaults.Retry`. Inherited from defaults it applies to every HTTP request that has an expectation, so writes are re-sent too and repeat their side effects. A polled request also retries a wrong status that is not in `RetryOnStatus` (a 400 from a typo, for instance), so a mistake costs the whole attempt budget before the request fails.

A request that sets its own `Retry` replaces `Defaults.Retry` as a whole, so copy the fields you still want, or merge a YAML anchor (`<<: *default_retry`).
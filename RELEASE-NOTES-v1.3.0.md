### PayloadStash v1.3.0 — Release Notes

#### Overview
1.3.0 extends `Expect` so a config can assert more without a separate grading script: poll until assertions
pass, compare against captured values with their types kept, share assertions across requests, check sets and
object keys, compare one part of a response with another, and assert across all the responses in a sequence.

Every 1.2.0 config validates unchanged. One behaviour changes for existing configs: `::count` on a JSONPath that
matches nothing is now `0` instead of `null` (see *Behaviour change* below).

#### New

- **Poll until the assertions pass: `Retry.RetryOnExpectFailure`** (HTTP only). With `true`, a response that fails
  any of the request's assertions is retried like a status in `RetryOnStatus`, under the same `Attempts`, backoff and
  `MaxElapsedSeconds`. Request-time values (`when: request`, `$pattern`) are generated again before each attempt,
  so a request-time `timestamp` header is fresh on every poll; resolve-time and captured values stay the same.
  Captures and results come from the final response. Setting it on a request with no `Expect`, or on an AMQP
  request, is a validation error. Set it per request: inherited from `Defaults.Retry` it makes every HTTP request
  with an `Expect` poll, writes included.

- **Typed captured values: `{ $captured: KEY }`.** Written as a whole value in `Body`, `Headers`, `Query` or an
  `Expect` matcher, it inserts the captured value with its type intact (number, list, object, boolean), where
  `${captured:KEY}` inside `$pattern` always yields a string. `validate` rejects a `KEY` that no request in the
  config captures; a captured name with no value yet at run time resolves to `null`.

- **Shared assertions: `Defaults.Expect` and `SkipDefaultExpect`.** `Defaults.Expect` is prepended to every
  request's own `Expect` (HTTP and AMQP). A request with `SkipDefaultExpect: true` keeps only its own. The resolved
  config shows the combined list on each request.

- **Collection matchers: `unique`, `setEquals`, `containsAll`, `keysEqual`.** Elements are compared by value, so
  objects with the same keys in a different order are equal. A failure names the missing, unexpected or repeated
  elements. On a JSONPath that can match many nodes (`[*]`, `.*`, a filter, a slice, `..`, a union), `unique`,
  `setEquals` and `containsAll` read the matches as a list: one match is a one-element list and no match is an
  empty list, so `{ setEquals: [] }` asserts that nothing matches. Other matchers on the same path still see a
  scalar for one match and `null` for none.

- **Compare against another part of the same response: `{ $jsonpath: EXPR }` as an expected value**, for example
  `"$.items[*]::count": { equals: { $jsonpath: "$.total" } }`. A failure prints both sides.

- **Sequence-level `Expect`.** Assertions on a sequence run after all its requests, against
  `{ "captured": {…}, "requests": [ { key, status, duration_ms, headers, body }, … ] }`, so a concurrent sequence
  can assert that exactly one request won. Results appear in the log, the report and the CSV, and count toward the
  exit code. A dry run skips them.

#### Behaviour change

- **`::count` on zero matches is `0`, not `null`.** A 1.2.0 assertion of `"…::count": { exists: false }` (the old
  way to say "nothing matches") now fails; write `{ equals: 0 }`. A `Capture` of a `::count` path stores `0` for an
  empty set. Every other aggregation, and a path without one, still resolves to `null` when nothing matches.

#### Compatibility notes

- A sequence with an `Expect` adds one row to the results CSV, with request `<Name> (sequence)`, an empty status
  and 0 attempts. Scripts that map every CSV row to a request should skip it. Configs without a sequence `Expect`
  write no such row.
- Request-level `Headers`, `Body` and `Query` replace the default section; they are not merged with it (unchanged
  from 1.2.0, now documented with an anchor example). A polled request that adds one header must repeat the
  default headers it needs.
- Retries without `RetryOnExpectFailure` (status, network and timeout retries) re-send the first attempt unchanged,
  as in 1.2.0.

#### Testing

- `tests/test_expect_features.py` covers each feature with a passing and a failing case, against a local HTTP
  server for the end-to-end cases. It now fails under pytest as well as when run as a script.
- A new workflow, `.github/workflows/tests.yml`, runs all five test scripts on every pull request and push to
  `main`. The release workflow still runs them before publishing an image.

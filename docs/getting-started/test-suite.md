# Use PayloadStash as a test suite

One of PayloadStash's primary use cases is testing systems that expose HTTP endpoints, exchange AMQP messages, or combine both transports. A YAML configuration acts as an executable test suite: operations exercise the system, captures preserve state between steps, expectations define pass or fail behavior, and the CLI exit status integrates with scripts and automation.

## Map test concepts to PayloadStash

| Test-suite concept | PayloadStash construct |
| --- | --- |
| Suite | One `StashConfig` |
| Scenario or group | A named sequence |
| Test case or step | A named HTTP or AMQP request |
| Setup and shared policy | `Defaults`, `Forced`, secrets, and dynamic values |
| State passed between steps | `Capture` values |
| Assertion | An `Expect` entry |
| Pass or fail result | Process exit status and expectation counts |
| Test evidence | Resolved YAML, CSV results, logs, reports, and response files |

## Test complete system behavior

A suite can test more than isolated endpoints. Sequential scenarios can create data over HTTP, capture an identifier, use it in later API calls, publish a related AMQP message, and verify each observed result. Concurrent sequences can apply controlled parallel traffic or validate independent cases more quickly.

Use expectations to define the contract that matters to the system under test:

- HTTP status codes, headers, body values, data types, and response time limits
- AMQP publish acknowledgements, routing outcomes, replies, and matched messages
- Captured values that must remain consistent across stateful operations
- Negative conditions, missing values, collection lengths, numeric ranges, and regular expressions

See [Expectations](../configuration/expectations.md) for every matcher and [Capture values](../configuration/capture.md) for stateful scenarios.

## Run the suite

Validate the configuration without contacting the target system:

```bash
payloadstash validate ./config/system-tests.yml --secrets ./config/secrets.env
```

Execute it and retain the evidence:

```bash
payloadstash run ./config/system-tests.yml \
  --out ./test-results \
  --yes \
  --secrets ./config/secrets.env
```

A successful run returns `0`. Failed expectations return `1`, while configuration or output setup failures return `9`. Individual operation errors are recorded and execution continues, so add explicit expectations for every condition that must fail the suite.

## Use the results locally or in automation

The exit status makes a suite suitable for shell scripts, CI jobs, deployment checks, scheduled probes, and agent-driven validation. The output directory retains a Markdown report for people, CSV results for automation, detailed logs, the effective redacted configuration, and response bodies for diagnosis.

Because the same YAML runs natively, in a container, or from an offline package, teams can use one test definition in a developer checkout, a controlled network, or an air-gapped environment.

Next, review the [HTTP](../examples/http-workflow.md) and [AMQP](../examples/amqp-workflow.md) examples, then [validate and run](run.md) your suite.

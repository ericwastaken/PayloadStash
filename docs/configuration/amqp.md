# AMQP requests

Set `Transport: amqp` to publish through RabbitMQ-compatible AMQP rather than make an HTTP request. AMQP-only configurations do not need `URLRoot`.

```yaml
StashConfig:
  Name: Publisher
  Defaults:
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
    AMQP:
      URI: "{ $secrets: RMQ_URI }"
      Exchange: events.topic
      Confirm: true
  Sequences:
    - Name: Publish
      Type: Sequential
      Requests:
        - UserCreated:
            Transport: amqp
            AMQP:
              RoutingKey: user.created
              Properties:
                DeliveryMode: persistent
                ContentType: application/json
                CorrelationId: { $pattern: "${uuidv4}" }
                Headers:
                  x-source: payloadstash
            Body:
              userId: 42
            Expect:
              - status: ack
```

## Routing and confirmation

- `URI` must be available after defaults/request/forced merging.
- At least one of `Exchange` or `RoutingKey` must be non-empty. An empty exchange with a routing key uses the default exchange; an exchange alone supports fanout publishing.
- `Confirm: true` waits for publisher confirmation and reports `ack` or `nack`.
- `Mandatory: true` reports unroutable messages as `unroutable`.
- Without confirmation, a completed publish reports `published`.

AMQP result metadata is exposed as response-like headers including `x-amqp-exchange`, `x-amqp-routing-key`, `x-amqp-confirmed`, and `x-amqp-routed`, so it can be captured or asserted.

## Message properties

Supported properties include `ContentType`, `ContentEncoding`, `DeliveryMode` (`transient` or `persistent`), `Priority` (0–9), `CorrelationId`, `ReplyTo`, `Expiration`, `MessageId`, `Type`, `AppId`, and application `Headers`. Nested property headers deep-merge across defaults, request values, and forced values.

## TLS

Use an `amqps://` URI and configure the optional TLS block:

```yaml
AMQP:
  URI: "{ $secrets: RMQ_URI }"
  TLS:
    CAFile: ./certs/ca.pem
    CertFile: ./certs/client.pem
    KeyFile: ./certs/client-key.pem
    VerifyPeer: true
```

Certificate paths are resolved from the process working directory. Keep `VerifyPeer: true` outside controlled local testing.

## Wait for a reply or message

`WaitFor` turns publish-and-wait into one operation:

=== "RPC"

    ```yaml
    AMQP:
      Exchange: ""
      RoutingKey: rpc.resolve
      WaitFor:
        Mode: rpc
        TimeoutSeconds: 5
    ```

    PayloadStash creates an exclusive reply queue and correlates the response. A received reply has status `reply`.

=== "Subscribe"

    ```yaml
    AMQP:
      Exchange: commands
      RoutingKey: refresh
      WaitFor:
        Mode: subscribe
        Exchange: events.fanout
        RoutingKey: ""
        TimeoutSeconds: 5
        Match:
          - "$.event": { equals: state_update }
    ```

    PayloadStash binds a temporary queue before publishing and waits for a matching message. A match has status `matched`; timeout and error statuses are available to expectations.
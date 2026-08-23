# AMQP workflow example

This AMQP test publishes three messages concurrently and requires a broker acknowledgement for every test case.

```yaml
dynamics:
  patterns:
    event_id:
      template: "evt-${uuidv4}"

StashConfig:
  Name: EventBurst
  Defaults:
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
    AMQP:
      URI: "{ $secrets: RMQ_URI }"
      Exchange: events.topic
      Confirm: true
      Properties:
        DeliveryMode: persistent
        ContentType: application/json
  Forced:
    AMQP:
      Properties:
        Headers:
          x-source: payloadstash
  Sequences:
    - Name: PublishEvents
      Type: Concurrent
      ConcurrencyLimit: 3
      Requests:
        - EventOne:
            Transport: amqp
            AMQP: { RoutingKey: demo.created }
            Body: { id: { $dynamic: event_id, when: request }, number: 1 }
            Expect: [{ status: ack }]
        - EventTwo:
            Transport: amqp
            AMQP: { RoutingKey: demo.created }
            Body: { id: { $dynamic: event_id, when: request }, number: 2 }
            Expect: [{ status: ack }]
        - EventThree:
            Transport: amqp
            AMQP: { RoutingKey: demo.created }
            Body: { id: { $dynamic: event_id, when: request }, number: 3 }
            Expect: [{ status: ack }]
```

```bash
payloadstash run ./events.yml --out ./output --yes --secrets ./secrets.env
```

Set `RMQ_URI` in `secrets.env`. The exchange and binding must already exist; PayloadStash publishes messages but does not provision broker topology. A missing acknowledgement fails its expectation and produces a failing suite result.

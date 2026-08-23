# HTTP workflow example

This sequential HTTP test creates an object, captures its identifier, and verifies that the target system returns the same identifier in a later request.

```yaml
dynamics:
  patterns:
    request_id:
      template: "req-${uuidv4}"

StashConfig:
  Name: InventoryWorkflow
  Defaults:
    URLRoot: https://api.example.com/v1
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 10 }
    Headers:
      Accept: application/json
    Retry:
      Attempts: 3
      BackoffStrategy: exponential
      BackoffSeconds: 0.5
      RetryOnStatus: [429, 500, 502, 503, 504]
  Forced:
    Headers:
      Authorization: "Bearer { $secrets: AUTH_TOKEN }"
  Sequences:
    - Name: CreateThenRead
      Type: Sequential
      Requests:
        - Create:
            Method: POST
            URLPath: /items
            Headers:
              Content-Type: application/json
            Body:
              name: demo
              requestId: { $dynamic: request_id, when: request }
            Capture:
              itemId: body.id
            Expect:
              - status: 201
              - body.id: { exists: true }
        - Read:
            Method: GET
            URLPath: /items/lookup
            Query:
              id: { $pattern: "${captured:itemId}" }
            Expect:
              - status: 200
              - body.id: { equals: { $pattern: "${captured:itemId}" } }
```

Run it with a secrets file:

```bash
payloadstash validate ./inventory.yml --secrets ./secrets.env
payloadstash run ./inventory.yml --out ./output --yes --secrets ./secrets.env
```

Replace the example endpoint and expectations with the contract required by the API under test. A failed expectation makes the suite return a failing exit status.

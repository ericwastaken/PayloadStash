# Examples

Start with the test-suite workflow matching the system under test:

- [HTTP workflow](http-workflow.md): test a stateful create/read path by capturing and reusing a response identifier.
- [AMQP workflow](amqp-workflow.md): test publishing behavior with broker confirmation and generated metadata.

The repository also maintains an executable [`config/config-example.yml`](https://github.com/ericwastaken/PayloadStash/blob/main/config/config-example.yml) and a developer-oriented AMQP integration harness. Copy examples before adding service addresses or secrets.

# AMQP Integration Test Harness

A local RabbitMQ broker (via Docker) plus scripts to exercise a PayloadStash **AMQP** config
end-to-end: publish messages, then confirm they actually landed on the broker with the right
routing, headers, and payloads. There is also an optional **amqps (TLS) + private-CA** variant.

This complements the offline unit tests in `../tests/test_amqp.py` (which use a fake broker) by
running against a real RabbitMQ.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose up --wait`).
- PayloadStash installed with `pika` (the repo `.venv` already has it). The scripts default to
  `../.venv/bin/payloadstash` and `../.venv/bin/python`; override with `PAYLOADSTASH=` / `PYTHON=`
  env vars if yours live elsewhere (e.g. `PAYLOADSTASH=payloadstash`).

## Quick start (plaintext)

```bash
cd amqp-test
./run-test.sh
```

That script runs four steps and prints `PASS` if all expected messages were delivered:

1. `docker compose up -d --wait` — boot RabbitMQ (waits for the healthcheck).
2. `declare.py` — declare the exchanges/queues/bindings the config targets, and purge them.
3. `payloadstash run ./amqp-test.yml --out ./out --secrets ./secrets.env --yes` — publish.
4. `drain.py` — read the queues and assert the expected message counts.

The broker is left running afterward so you can inspect it. Stop it with:

```bash
docker compose down
```

## What gets published

`amqp-test.yml` is an **AMQP-only** config (no `URLRoot`). With `Confirm: true`, every publish waits
for a broker ack — so a green run already proves the broker accepted and routed each message; `drain.py`
then proves delivery. The topology `declare.py` sets up:

| Queue | Exchange | Binding key | Messages from the run |
|---|---|---|---|
| `test.coin` | `frontline.exchange` (topic) | `device.signal.coin` | 1 (the `emit-coin` publish) |
| `test.banana` | `frontline.exchange` (topic) | `device.signal.banana` | 3 (the concurrent burst) |
| `test.state` | `state.fanout` (fanout) | — | 1 (the fanout broadcast) |

## Inspect it yourself

- **Management UI:** http://localhost:15672 (user `guest` / pass `guest`) — see exchanges, queues,
  message rates, and use "Get messages" on a queue.
- **Run artifacts:** `out/<Name>/<timestamp>/` — resolved config, run log (shows each `ack`), results
  CSV, and per-request report.

## Manual run (instead of the script)

```bash
cp secrets.env.example secrets.env          # first time only (secrets.env is git-ignored)
docker compose up -d --wait
../.venv/bin/python declare.py
../.venv/bin/payloadstash run ./amqp-test.yml --out ./out --secrets ./secrets.env --yes
../.venv/bin/python drain.py
docker compose down          # when finished
```

The `run-*.sh` scripts create `secrets.env` from `secrets.env.example` automatically.

## TLS / amqps with a private CA (optional)

Exercises the `AMQP.TLS` block: the broker presents a cert signed by a throwaway CA, and PayloadStash
verifies it against that CA (`VerifyPeer: true`).

```bash
cd amqp-test
docker compose down                 # stop the plaintext broker first (same container/ports)
./run-test-tls.sh
```

It generates test certs (`tls/gen-certs.sh` → `tls/certs/`), boots the TLS broker (`compose.tls.yml`,
listening on both `5671`/amqps and `5672`/plaintext), declares/drains over plaintext, and **publishes
over amqps** using `amqp-test-tls.yml` + `secrets-tls.env`. Stop with:

```bash
docker compose -f compose.tls.yml down
```

The CA verification is real: publishing to this broker with `VerifyPeer: true` and **no** `CAFile`
fails with an SSL certificate-verification error (the private CA isn't in the system trust store);
adding `CAFile: tls/certs/ca.pem` makes it succeed. `VerifyPeer: false` connects without verifying.
The test certs are self-signed throwaways and are git-ignored — never use them in production.

## RPC + WaitFor (rpc & subscribe)

Exercises `AMQP.WaitFor` against a real broker, using a background responder.

```bash
cd amqp-test
docker compose down          # if a broker from another test is running
./run-test-waitfor.sh
```

It boots the broker, starts `responder.py` (an RPC echo + a `device.signal.*` → `state.fanout`
rebroadcaster), then runs `amqp-test-waitfor.yml`, which:

1. **rpc** — publishes to `rpc.resolve`, awaits the correlated reply, and `Capture`s a `playFabId`
   from the reply body (asserts `status: reply`).
2. **subscribe** — publishes a `device.signal.coin` trigger and awaits the `state_update` broadcast
   the responder emits to `state.fanout` (asserts `status: matched` and that the captured `playFabId`
   round-tripped through the broadcast).

The PayloadStash `Expect` assertions are the test — a `0` exit means they all passed. Stop with
`docker compose down` (the responder is stopped automatically).

## Point it at your own broker

Set `RMQ_URI` (used by `declare.py`/`drain.py`) and edit `secrets.env` (used by PayloadStash), then
skip the `docker compose` steps:

```bash
export RMQ_URI="amqp://user:pass@my-broker:5672/%2F"
cp secrets.env.example secrets.env   # then edit secrets.env to match RMQ_URI
../.venv/bin/python declare.py
../.venv/bin/payloadstash run ./amqp-test.yml --out ./out --secrets ./secrets.env --yes
../.venv/bin/python drain.py
```

## Files

| File | Purpose |
|---|---|
| `compose.yml` | Plaintext RabbitMQ broker (5672 + 15672 management) |
| `rabbitmq/rabbitmq.conf` | `loopback_users = none` so `guest` works from the host |
| `declare.py` | Declare + purge exchanges/queues/bindings |
| `drain.py` | Read queues and assert expected message counts |
| `amqp-test.yml` | The PayloadStash AMQP config under test |
| `secrets.env.example` | Template for `secrets.env` (git-ignored); `RMQ_URI` for the plaintext broker |
| `run-test.sh` | One-shot: boot → declare → publish → verify |
| `compose.tls.yml`, `rabbitmq/rabbitmq-tls.conf` | TLS broker (adds 5671/amqps) |
| `tls/gen-certs.sh` | Generate a throwaway CA + server cert (SAN=localhost) |
| `amqp-test-tls.yml`, `secrets-tls.env.example` | amqps config + broker URI template |
| `run-test-tls.sh` | One-shot TLS variant |
| `responder.py` | Background RPC echo + signal→fanout rebroadcaster (for WaitFor) |
| `amqp-test-waitfor.yml` | WaitFor config: rpc → capture → subscribe |
| `run-test-waitfor.sh` | One-shot RPC + WaitFor variant |

`out/`, `tls/certs/`, `secrets.env`, and `secrets-tls.env` are git-ignored (only the `*.example`
templates are committed).

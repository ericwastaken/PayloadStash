#!/usr/bin/env python3
"""Declare the exchanges, queues, and bindings the AMQP test config publishes to.

Idempotent, and purges the test queues so message counts are exact on each run.
Connects with RMQ_URI (default: amqp://guest:guest@localhost:5672/%2F).
"""
import os
import sys
import pika

URI = os.environ.get("RMQ_URI", "amqp://guest:guest@localhost:5672/%2F")

# (exchange, type)
EXCHANGES = [
    ("frontline.exchange", "topic"),
    ("state.fanout", "fanout"),
]
# (queue, exchange, binding_key)
BINDINGS = [
    ("test.coin", "frontline.exchange", "device.signal.coin"),
    ("test.banana", "frontline.exchange", "device.signal.banana"),
    ("test.state", "state.fanout", ""),
]


def main():
    conn = pika.BlockingConnection(pika.URLParameters(URI))
    ch = conn.channel()
    for name, kind in EXCHANGES:
        ch.exchange_declare(exchange=name, exchange_type=kind, durable=True)
    for queue, exchange, key in BINDINGS:
        ch.queue_declare(queue=queue, durable=True)
        ch.queue_purge(queue=queue)  # clean slate for exact counts
        ch.queue_bind(queue=queue, exchange=exchange, routing_key=key)
    conn.close()
    print("Declared %d exchanges and %d queues/bindings (queues purged)."
          % (len(EXCHANGES), len(BINDINGS)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("declare.py failed: %s" % e, file=sys.stderr)
        sys.exit(1)

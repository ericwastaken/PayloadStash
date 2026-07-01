#!/usr/bin/env python3
"""Drain the test queues and verify the AMQP test run delivered the expected messages.

Reads every message from each test queue, prints a short summary, and asserts the
expected minimum counts. Exit 0 = all expected messages arrived; exit 1 = mismatch.
Connects with RMQ_URI (default: amqp://guest:guest@localhost:5672/%2F).
"""
import os
import sys
import json
import pika

URI = os.environ.get("RMQ_URI", "amqp://guest:guest@localhost:5672/%2F")

# queue -> expected message count for the shipped amqp-test.yml
EXPECTED = {
    "test.coin": 1,
    "test.banana": 3,
    "test.state": 1,
}


def drain(ch, queue):
    msgs = []
    while True:
        method, props, body = ch.basic_get(queue=queue, auto_ack=True)
        if method is None:
            break
        try:
            payload = json.loads(body)
        except Exception:
            payload = body.decode("utf-8", "replace")
        msgs.append((props, payload))
    return msgs


def main():
    conn = pika.BlockingConnection(pika.URLParameters(URI))
    ch = conn.channel()
    ok = True
    for queue, expected in EXPECTED.items():
        msgs = drain(ch, queue)
        got = len(msgs)
        status = "OK" if got >= expected else "MISSING"
        if got < expected:
            ok = False
        print("[%s] %s: %d message(s) (expected >= %d)" % (status, queue, got, expected))
        for props, payload in msgs:
            hdrs = getattr(props, "headers", None) or {}
            cid = getattr(props, "correlation_id", None)
            print("    - correlation_id=%s headers=%s body=%s"
                  % (cid, hdrs, json.dumps(payload) if isinstance(payload, (dict, list)) else payload))
    conn.close()
    print("\n%s" % ("ALL EXPECTED MESSAGES DELIVERED" if ok else "MISSING MESSAGES — check the run log"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

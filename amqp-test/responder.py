#!/usr/bin/env python3
"""Test responder for the WaitFor integration test. Two behaviours:

- RPC: consumes the `rpc.resolve` queue and replies to `reply_to` with the same correlation_id,
  echoing a PlayFabId derived from the request's bandId.
- Signal -> broadcast: consumes `device.signal.*` from `frontline.exchange` and re-emits a
  `state_update` to the `state.fanout` exchange (this is what a `WaitFor: subscribe` awaits).

Run it in the background before publishing. Ctrl-C / kill to stop.
Connects with RMQ_URI (default: amqp://guest:guest@localhost:5672/%2F).
"""
import os
import sys
import json
import time
import pika

URI = os.environ.get("RMQ_URI", "amqp://guest:guest@localhost:5672/%2F")


def connect():
    last = None
    for _ in range(20):
        try:
            return pika.BlockingConnection(pika.URLParameters(URI))
        except Exception as e:
            last = e
            time.sleep(0.5)
    raise last


def on_rpc(ch, method, props, body):
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    reply = json.dumps({"result": {"PlayFabId": "PF-%s" % data.get("bandId", "unknown")}})
    ch.basic_publish(
        exchange="",
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id, content_type="application/json"),
        body=reply,
    )
    ch.basic_ack(method.delivery_tag)
    print("responder: replied to rpc (corr=%s)" % props.correlation_id, flush=True)


def on_signal(ch, method, props, body):
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    evt = json.dumps({"event": "state_update", "playFabId": data.get("playFabId"), "action": data.get("action")})
    ch.basic_publish(exchange="state.fanout", routing_key="", body=evt,
                     properties=pika.BasicProperties(content_type="application/json"))
    ch.basic_ack(method.delivery_tag)
    print("responder: rebroadcast state_update to state.fanout", flush=True)


def main():
    conn = connect()
    ch = conn.channel()
    ch.exchange_declare("frontline.exchange", "topic", durable=True)
    ch.exchange_declare("state.fanout", "fanout", durable=True)
    ch.queue_declare(queue="rpc.resolve", durable=False)
    ch.queue_declare(queue="signal.work", durable=False)
    ch.queue_bind("signal.work", "frontline.exchange", "device.signal.*")
    ch.basic_consume("rpc.resolve", on_rpc)
    ch.basic_consume("signal.work", on_signal)
    print("responder ready", flush=True)
    try:
        ch.start_consuming()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

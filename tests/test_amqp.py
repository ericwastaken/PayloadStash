"""Phase 1 AMQP tests — schema validation/resolution + AmqpManager status mapping.

Plain-script style (matching tests/test_asserts.py); no pytest dependency, no live broker
(the publish paths are exercised with a fake pika connection).

Run:  .venv/bin/python tests/test_amqp.py
"""
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payload_stash.config_schema import validate_config_data, build_resolved_config_dict
from payload_stash import amqp_manager
from payload_stash.amqp_manager import AmqpManager
import pika
from pika import exceptions as pika_exc

_URI = "amqp://guest:guest@localhost:5672/%2F"

_results = []


def check(name, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), name)
    return cond


def expect_fail(name, y):
    try:
        validate_config_data(yaml.safe_load(y))
        return check(name + " (should reject)", False)
    except Exception:
        return check(name + " (rejected)", True)


# --------------------------------------------------------------------------- schema

def test_schema():
    # 1) bare HTTP config still validates unchanged (Transport defaults to http)
    http = """
StashConfig:
  Name: h
  Defaults: { URLRoot: https://x, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Method: GET, URLPath: /a } } ]}
"""
    cfg = validate_config_data(yaml.safe_load(http))
    r = build_resolved_config_dict(cfg)
    req = r["StashConfig"]["Sequences"][0]["Requests"][0]["r"]
    check("bare HTTP validates + resolved unchanged", req.get("Method") == "GET" and "URLRoot" in req)

    # 2) mixed HTTP+AMQP config
    mixed = """
StashConfig:
  Name: m
  Defaults:
    URLRoot: https://x
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }
    AMQP: { URI: "%s", Confirm: true }
  Forced:
    AMQP: { Properties: { Headers: { x-run: smoke } } }
  Sequences:
    - Name: s
      Type: Sequential
      Requests:
        - pub:
            Transport: amqp
            AMQP:
              Exchange: ex
              RoutingKey: rk
              Properties: { DeliveryMode: persistent, Headers: { x-source: ps } }
            Body: { a: 1 }
        - get: { Method: GET, URLPath: /a }
""" % _URI
    cfg = validate_config_data(yaml.safe_load(mixed))
    r = build_resolved_config_dict(cfg)
    reqs = r["StashConfig"]["Sequences"][0]["Requests"]
    amqp_req = reqs[0]["pub"]
    http_req = reqs[1]["get"]
    check("mixed: amqp Transport tag", amqp_req.get("Transport") == "amqp")
    check("mixed: amqp has no HTTP injection", "URLRoot" not in amqp_req and "InsecureTLS" not in amqp_req)
    check("mixed: Confirm inherited from Defaults", amqp_req["AMQP"].get("Confirm") is True)
    check("mixed: Properties.Headers deep-merged",
          amqp_req["AMQP"]["Properties"]["Headers"] == {"x-source": "ps", "x-run": "smoke"})
    check("mixed: DeliveryMode dumped as value", amqp_req["AMQP"]["Properties"]["DeliveryMode"] == "persistent")
    check("mixed: HTTP request intact", http_req.get("Method") == "GET" and "URLRoot" in http_req)

    # 3) AMQP-only config may omit URLRoot; fanout (exchange-only) accepted
    amqp_only = """
StashConfig:
  Name: a
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }, AMQP: { URI: "%s" } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Transport: amqp, AMQP: { Exchange: ex.fanout } } } ]}
""" % _URI
    try:
        validate_config_data(yaml.safe_load(amqp_only))
        check("AMQP-only config valid w/o URLRoot (fanout)", True)
    except Exception as e:
        check("AMQP-only config valid w/o URLRoot (fanout): %s" % e, False)

    # 4) negative cases
    expect_fail("amqp: both Exchange+RoutingKey empty", """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }, AMQP: { URI: "x" } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Transport: amqp, AMQP: { Exchange: "" } } } ]}
""")
    expect_fail("amqp: no broker URI", """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Transport: amqp, AMQP: { RoutingKey: q } } } ]}
""")
    expect_fail("amqp: HTTP-only key Method rejected", """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }, AMQP: { URI: "x" } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Transport: amqp, Method: GET, AMQP: { RoutingKey: q } } } ]}
""")
    expect_fail("http: unknown AMQP key on http request rejected", """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://x, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Method: GET, URLPath: /a, AMQP: { RoutingKey: q } } } ]}
""")


# --------------------------------------------------------------------------- manager (fake broker)

class _FakeChannel:
    def __init__(self, outcome):
        self.outcome = outcome
        self.confirm_enabled = False
        self.published = None

    def confirm_delivery(self):
        self.confirm_enabled = True

    def basic_publish(self, exchange, routing_key, body, properties, mandatory=False):
        self.published = dict(exchange=exchange, routing_key=routing_key, body=body,
                              properties=properties, mandatory=mandatory)
        if self.outcome == "nack":
            raise pika_exc.NackError([])
        if self.outcome == "unroutable":
            raise pika_exc.UnroutableError([])


class _FakeConn:
    def __init__(self, ch):
        self._ch = ch
        self.closed = False

    def channel(self):
        return self._ch

    def close(self):
        self.closed = True


def _patched_publish(outcome, **kw):
    """Run AmqpManager.publish against a fake channel with the given outcome."""
    ch = _FakeChannel(outcome)
    conn = _FakeConn(ch)
    orig = pika.BlockingConnection
    pika.BlockingConnection = lambda params: conn
    try:
        am = AmqpManager()
        result = am.publish(uri=_URI, exchange=kw.get("exchange", "ex"),
                            routing_key=kw.get("routing_key", "rk"),
                            body=kw.get("body", b'{"a":1}'),
                            properties=kw.get("properties"),
                            confirm=kw.get("confirm", False),
                            mandatory=kw.get("mandatory", False),
                            timeout_s=kw.get("timeout_s", 5))
        return result, ch, conn
    finally:
        pika.BlockingConnection = orig


def test_manager():
    # properties mapping
    am = AmqpManager()
    props = am._build_properties({"DeliveryMode": "persistent", "ContentType": "application/json",
                                  "CorrelationId": "cid-1", "Headers": {"k": "v"}})
    check("delivery_mode persistent -> 2", props.delivery_mode == 2)
    check("content_type mapped", props.content_type == "application/json")
    check("correlation_id mapped", props.correlation_id == "cid-1")
    check("headers mapped", props.headers == {"k": "v"})

    # status mapping via fake channel
    (status, headers, text, attempts, log), ch, conn = _patched_publish("ok", confirm=True)
    check("confirm success -> ack", status == "ack" and headers.get("x-amqp-confirmed") == "true")
    check("confirm enabled channel", ch.confirm_enabled is True)
    check("connection closed after publish", conn.closed is True)
    check("routing headers synthesized (lowercase)",
          headers.get("x-amqp-exchange") == "ex" and headers.get("x-amqp-routing-key") == "rk")

    (status, headers, *_), ch, _ = _patched_publish("nack", confirm=True)
    check("confirm nack -> nack", status == "nack")

    (status, headers, *_), ch, _ = _patched_publish("unroutable", mandatory=True)
    check("mandatory unroutable -> unroutable", status == "unroutable" and headers.get("x-amqp-routed") == "false")
    check("mandatory enabled confirm", ch.confirm_enabled is True)

    (status, headers, *_), ch, _ = _patched_publish("ok")  # neither confirm nor mandatory
    check("fire-and-forget -> published", status == "published")
    check("fire-and-forget did not enable confirm", ch.confirm_enabled is False)

    # missing URI -> raises with attempts_made/request_log attached
    try:
        AmqpManager().publish(uri=None, exchange="ex", routing_key="rk")
        check("missing URI raises", False)
    except Exception as e:
        check("missing URI raises w/ attempts_made", getattr(e, "attempts_made", None) == 1)

    # default content-type applied when body present and unset
    (_, _, _, _, _), ch, _ = _patched_publish("ok", confirm=True, body=b'{"x":1}', properties={})
    check("default content_type json applied", ch.published["properties"].content_type == "application/json")


def test_tls():
    am = AmqpManager()
    # plain amqp -> no TLS
    check("amqp:// -> no ssl options", am._ssl_options("amqp://h:5672/%2F", None, "h") is None)

    # amqps default -> verify on, hostname from URI
    opts = am._ssl_options("amqps://broker.internal:5671/%2F", None, "broker.internal")
    import ssl as _ssl
    check("amqps default -> SSLOptions built", opts is not None)
    check("amqps default -> verify required", opts.context.verify_mode == _ssl.CERT_REQUIRED)
    check("amqps default -> check_hostname on", opts.context.check_hostname is True)
    check("amqps default -> server_hostname from URI host", opts.server_hostname == "broker.internal")

    # VerifyPeer false -> verification disabled
    opts = am._ssl_options("amqps://broker.internal:5671/%2F", {"VerifyPeer": False}, "broker.internal")
    check("VerifyPeer false -> CERT_NONE", opts.context.verify_mode == _ssl.CERT_NONE)
    check("VerifyPeer false -> check_hostname off", opts.context.check_hostname is False)

    # ServerName override
    opts = am._ssl_options("amqps://10.0.0.5:5671/%2F", {"ServerName": "rabbit.park.com"}, "10.0.0.5")
    check("ServerName override honored", opts.server_hostname == "rabbit.park.com")

    # schema accepts a TLS block and it survives resolution
    y = """
StashConfig:
  Name: t
  Defaults:
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }
    AMQP:
      URI: "amqps://broker:5671/%2F"
      TLS: { CAFile: /etc/ssl/ca.pem, VerifyPeer: true }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { r: { Transport: amqp, AMQP: { RoutingKey: q } } } ]}
"""
    cfg = validate_config_data(yaml.safe_load(y))
    r = build_resolved_config_dict(cfg)
    amqp = r["StashConfig"]["Sequences"][0]["Requests"][0]["r"]["AMQP"]
    check("TLS block resolved into AMQP", amqp.get("TLS", {}).get("CAFile") == "/etc/ssl/ca.pem")


def test_waitfor_schema():
    base = """
StashConfig:
  Name: t
  Defaults: {{ FlowControl: {{ DelaySeconds: 0, TimeoutSeconds: 5 }}, AMQP: {{ URI: "amqp://x" }} }}
  Sequences:
    - Name: s
      Type: Sequential
      Requests:
        - r:
            Transport: amqp
            AMQP: {{ Exchange: "", RoutingKey: rpc.q, WaitFor: {wf} }}
"""
    def valid(wf):
        try:
            validate_config_data(yaml.safe_load(base.format(wf=wf))); return True
        except Exception:
            return False
    check("WaitFor rpc valid", valid("{ Mode: rpc }"))
    check("WaitFor subscribe valid",
          valid('{ Mode: subscribe, Exchange: state.fanout, Match: [ { "$.ok": { equals: true } } ] }'))
    check("WaitFor rpc+Match rejected", not valid("{ Mode: rpc, Match: [ { status: reply } ] }"))
    check("WaitFor subscribe w/o Match rejected", not valid("{ Mode: subscribe, Exchange: state.fanout }"))
    check("WaitFor subscribe w/o Exchange rejected",
          not valid('{ Mode: subscribe, Match: [ { "$.ok": { equals: true } } ] }'))


# ---- fake broker that supports the consume loop used by _single_waitfor -----------------

class _FakeMethod:
    def __init__(self, delivery_tag=1, routing_key=""):
        self.delivery_tag = delivery_tag
        self.routing_key = routing_key


class _FakeProps:
    def __init__(self, correlation_id=None, content_type=None, headers=None, reply_to=None):
        self.correlation_id = correlation_id
        self.content_type = content_type
        self.headers = headers
        self.reply_to = reply_to


class _WFChannel:
    def __init__(self):
        self.connection = None
        self._cb = None
        self._pending = []      # (method, props, body) awaiting delivery to the consumer
        self.published = []
        self.rpc_reply = b'{"result": {"PlayFabId": "PF-1"}}'   # echoed on rpc publish; None => no reply
        self._tag = 0
        self._qn = 0

    def _q(self):
        self._qn += 1
        r = type("R", (), {})()
        r.method = type("M", (), {"queue": "amq.gen-%d" % self._qn})()
        return r

    def queue_declare(self, queue="", exclusive=False, durable=False, auto_delete=False):
        return self._q()

    def queue_bind(self, queue, exchange, routing_key=""):
        pass

    def basic_publish(self, exchange, routing_key, body, properties=None, mandatory=False):
        self.published.append((exchange, routing_key, body, properties, mandatory))
        rt = getattr(properties, "reply_to", None)
        if rt and self.rpc_reply is not None:          # rpc: echo a correlated reply
            self._tag += 1
            m = _FakeMethod(self._tag, rt)
            p = _FakeProps(correlation_id=getattr(properties, "correlation_id", None),
                           content_type="application/json")
            self._pending.append((m, p, self.rpc_reply))

    def basic_consume(self, queue, on_message_callback, auto_ack=False):
        self._cb = on_message_callback
        return "ctag"

    def basic_cancel(self, tag):
        self._cb = None

    def basic_ack(self, delivery_tag):
        pass

    def _pump(self):
        if not self._cb or not self._pending:
            return 0
        batch, self._pending = self._pending, []
        for m, p, b in batch:
            self._cb(self, m, p, b)
        return len(batch)


class _WFConn:
    def __init__(self, ch):
        self._ch = ch
        ch.connection = self

    def channel(self):
        return self._ch

    def process_data_events(self, time_limit=0):
        import time as _t
        if self._ch._pump() == 0:
            _t.sleep(min(time_limit, 0.02))

    def close(self):
        pass


def _run_waitfor(ch, waitfor, **kw):
    conn = _WFConn(ch)
    orig = pika.BlockingConnection
    pika.BlockingConnection = lambda params: conn
    try:
        return AmqpManager().publish(
            uri="amqp://guest:guest@localhost:5672/%2F",
            exchange=kw.get("exchange", ""),
            routing_key=kw.get("routing_key", "rpc.q"),
            body=kw.get("body", b'{"bandId":"x"}'),
            waitfor=waitfor,
        )
    finally:
        pika.BlockingConnection = orig


def test_waitfor_manager():
    # props projection
    p = _FakeProps(correlation_id="c1", content_type="application/json", headers={"X-Event-Type": "state_update"})
    hdrs = AmqpManager._props_to_headers(p)
    check("props->headers lowercased + correlation", hdrs.get("x-event-type") == "state_update" and hdrs.get("x-correlation-id") == "c1")

    # rpc: reply received
    ch = _WFChannel()
    status, headers, text, attempts, log = _run_waitfor(ch, {"Mode": "rpc", "TimeoutSeconds": 0.5})
    check("rpc -> reply status", status == "reply")
    check("rpc reply body returned", '"PlayFabId": "PF-1"' in text)
    check("rpc set reply_to + correlation on request",
          getattr(ch.published[0][3], "reply_to", None) and getattr(ch.published[0][3], "correlation_id", None))
    check("rpc reply carries x-correlation-id", "x-correlation-id" in headers)
    check("rpc reply carries x-amqp-wait-ms", "x-amqp-wait-ms" in headers)

    # rpc: timeout (no reply staged)
    ch = _WFChannel(); ch.rpc_reply = None
    status, *_ = _run_waitfor(ch, {"Mode": "rpc", "TimeoutSeconds": 0.2})
    check("rpc -> timeout when no reply", status == "timeout")

    # subscribe: matching message (after one non-matching) -> matched
    ch = _WFChannel()
    ch._pending = [
        (_FakeMethod(1, "state.update"), _FakeProps(content_type="application/json"), b'{"playFabId":"OTHER"}'),
        (_FakeMethod(2, "state.update"), _FakeProps(content_type="application/json", headers={"x-event-type": "state_update"}), b'{"playFabId":"PF-9"}'),
    ]
    wf = {"Mode": "subscribe", "Exchange": "state.fanout", "RoutingKey": "#", "TimeoutSeconds": 0.5,
          "Match": [{"$.playFabId": {"equals": "PF-9"}}, {"headers.x-event-type": {"equals": "state_update"}}]}
    status, headers, text, *_ = _run_waitfor(ch, wf)
    check("subscribe -> matched status", status == "matched")
    check("subscribe matched body", '"playFabId":"PF-9"' in text or '"PF-9"' in text)
    check("subscribe counts non-matching", headers.get("x-amqp-nonmatching-count") == "1")
    check("subscribe binds before publishing (queue bound, trigger sent)", len(ch.published) == 1)
    check("subscribe matched carries x-amqp-wait-ms", "x-amqp-wait-ms" in headers)

    # subscribe: no match -> timeout
    ch = _WFChannel()
    ch._pending = [(_FakeMethod(1), _FakeProps(content_type="application/json"), b'{"playFabId":"NOPE"}')]
    wf = {"Mode": "subscribe", "Exchange": "state.fanout", "TimeoutSeconds": 0.2,
          "Match": [{"$.playFabId": {"equals": "PF-9"}}]}
    status, headers, *_ = _run_waitfor(ch, wf)
    check("subscribe -> timeout when nothing matches", status == "timeout")


if __name__ == "__main__":
    test_schema()
    test_manager()
    test_tls()
    test_waitfor_schema()
    test_waitfor_manager()
    total = len(_results)
    passed = sum(_results)
    print("\n%d/%d passed — %s" % (passed, total, "ALL GREEN" if passed == total else "RED"))
    sys.exit(0 if passed == total else 1)

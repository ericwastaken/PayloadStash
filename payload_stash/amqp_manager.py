"""
amqp_manager.py

AMQP publishing for PayloadStash — a sibling of request_manager.py.

Design mirrors RequestManager:
- Synchronous pika BlockingConnection, one connection per publish (thread-safe: a connection is
  never shared across the ThreadPoolExecutor workers used by Concurrent sequences).
- Implements its own fixed/exponential backoff + jitter for connection/publish errors, matching the
  Retry config schema. Broker decisions (nack / unroutable) are NOT retried — they are results.

Phase 1 scope: publish with optional publisher confirms and mandatory routing.
  RPC / WaitFor (awaiting a reply or a subscribed message) is Phase 2.

`publish` returns the same 5-tuple RequestManager.request returns:
    (status, headers_dict, body_text, attempts_made, request_log)
For AMQP, `status` is a string label rather than an HTTP int:
    "ack"        - publisher confirm: broker acknowledged
    "nack"       - publisher confirm: broker rejected
    "unroutable" - Mandatory=true and no queue was bound to route the message
    "published"  - fire-and-forget (no confirm requested); handed to the socket
Connection/auth/network failures raise (after retries) with .request_log / .attempts_made attached,
so the caller handles them exactly like an HTTP failure.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import time
import random
import uuid

import pika
from pika import exceptions as pika_exc

from .config_utility import evaluate_expect


# AMQP delivery mode label -> pika numeric value
_DELIVERY_MODE = {"transient": 1, "persistent": 2}

# Connection/publish exceptions that are transient and therefore retryable.
_RETRYABLE_EXCS: Tuple[type, ...] = (
    pika_exc.AMQPConnectionError,
    pika_exc.AMQPChannelError,
    pika_exc.StreamLostError,
    OSError,
)


class AmqpManager:
    def __init__(self) -> None:
        # No shared connection state — connections are opened per publish for thread-safety.
        pass

    def _build_properties(self, properties: Dict[str, Any]) -> "pika.BasicProperties":
        kwargs: Dict[str, Any] = {}
        if properties.get("ContentType") is not None:
            kwargs["content_type"] = str(properties["ContentType"])
        if properties.get("ContentEncoding") is not None:
            kwargs["content_encoding"] = str(properties["ContentEncoding"])
        dm = properties.get("DeliveryMode")
        if dm is not None:
            kwargs["delivery_mode"] = _DELIVERY_MODE.get(str(dm), 1)
        if properties.get("Priority") is not None:
            kwargs["priority"] = int(properties["Priority"])
        if properties.get("CorrelationId") is not None:
            kwargs["correlation_id"] = str(properties["CorrelationId"])
        if properties.get("ReplyTo") is not None:
            kwargs["reply_to"] = str(properties["ReplyTo"])
        if properties.get("Expiration") is not None:
            kwargs["expiration"] = str(properties["Expiration"])
        if properties.get("MessageId") is not None:
            kwargs["message_id"] = str(properties["MessageId"])
        if properties.get("Type") is not None:
            kwargs["type"] = str(properties["Type"])
        if properties.get("AppId") is not None:
            kwargs["app_id"] = str(properties["AppId"])
        hdrs = properties.get("Headers")
        if isinstance(hdrs, dict) and hdrs:
            kwargs["headers"] = dict(hdrs)
        return pika.BasicProperties(**kwargs)

    def _ssl_options(self, uri: str, tls: Optional[Dict[str, Any]], host: str):
        """Build pika.SSLOptions for an amqps:// broker. Returns None for plain amqp://.

        With a CAFile/CAPath the broker cert is verified against that CA (only that CA — point it at
        a bundle if you also need the system roots). CertFile/KeyFile enable mutual TLS. VerifyPeer=False
        disables verification. Hostname verification uses ServerName, defaulting to the URI host.
        """
        if not uri.lower().startswith("amqps://"):
            return None
        import ssl as _ssl

        tls = tls or {}
        cafile = tls.get("CAFile")
        capath = tls.get("CAPath")
        if cafile or capath:
            ctx = _ssl.create_default_context(cafile=cafile, capath=capath)
        else:
            ctx = _ssl.create_default_context()

        certfile = tls.get("CertFile")
        if certfile:
            ctx.load_cert_chain(certfile=certfile, keyfile=tls.get("KeyFile"))

        if tls.get("VerifyPeer") is False:
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE

        server_name = tls.get("ServerName") or host or None
        return pika.SSLOptions(ctx, server_hostname=server_name)

    def _single_publish(
        self,
        uri: str,
        exchange: str,
        routing_key: str,
        body: Optional[bytes],
        properties: Dict[str, Any],
        confirm: bool,
        mandatory: bool,
        timeout_s: Optional[float],
        tls: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, str], str]:
        # Default a JSON content-type when a body is present and none was specified.
        props_in = dict(properties or {})
        if body and not props_in.get("ContentType"):
            props_in["ContentType"] = "application/json"

        params = pika.URLParameters(uri)
        ssl_opts = self._ssl_options(uri, tls, getattr(params, "host", None))
        if ssl_opts is not None:
            params.ssl_options = ssl_opts
        if isinstance(timeout_s, (int, float)) and timeout_s > 0:
            # Bound how long we'll wait on a blocked connection / socket operations.
            try:
                params.blocked_connection_timeout = float(timeout_s)
            except Exception:
                pass
            try:
                params.socket_timeout = float(timeout_s)
            except Exception:
                pass

        base_headers: Dict[str, str] = {
            "x-amqp-exchange": exchange or "",
            "x-amqp-routing-key": routing_key or "",
        }

        conn = pika.BlockingConnection(params)
        try:
            ch = conn.channel()
            props = self._build_properties(props_in)
            # Confirms are needed to synchronously observe nacks; Mandatory needs them to observe
            # an unroutable return. Enable when either is requested.
            use_confirm = bool(confirm or mandatory)
            if use_confirm:
                ch.confirm_delivery()

            try:
                ch.basic_publish(
                    exchange=exchange or "",
                    routing_key=routing_key or "",
                    body=body or b"",
                    properties=props,
                    mandatory=bool(mandatory),
                )
            except pika_exc.UnroutableError:
                headers = dict(base_headers)
                headers["x-amqp-routed"] = "false"
                return "unroutable", headers, ""
            except pika_exc.NackError:
                headers = dict(base_headers)
                headers["x-amqp-confirmed"] = "false"
                return "nack", headers, ""

            headers = dict(base_headers)
            if confirm:
                headers["x-amqp-confirmed"] = "true"
                headers["x-amqp-routed"] = "true"
                return "ack", headers, ""
            headers["x-amqp-confirmed"] = "false"
            return "published", headers, ""
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _props_to_headers(p) -> Dict[str, str]:
        """Project a received message's BasicProperties into a lowercase headers dict for
        Capture/Expect/Match (`headers.<name>` paths resolve case-insensitively)."""
        out: Dict[str, str] = {}
        if p is None:
            return out
        ct = getattr(p, "content_type", None)
        if ct:
            out["content-type"] = str(ct)
        cid = getattr(p, "correlation_id", None)
        if cid:
            out["x-correlation-id"] = str(cid)
        app = getattr(p, "headers", None)
        if isinstance(app, dict):
            for k, v in app.items():
                out[str(k).lower()] = v
        return out

    def _consume_until(self, ch, queue: str, deadline_s: float, match) -> Optional[tuple]:
        """Consume messages from `queue`, acking each, until one satisfies match(method, props, body)
        or the deadline elapses. Non-matching messages are ack'd and discarded. Returns the matching
        (method, props, body) tuple, or None on timeout."""
        found: list = []

        def _cb(channel, method, properties, body):
            try:
                if match(method, properties, body):
                    found.append((method, properties, body))
            finally:
                try:
                    channel.basic_ack(method.delivery_tag)
                except Exception:
                    pass

        consumer_tag = ch.basic_consume(queue=queue, on_message_callback=_cb, auto_ack=False)
        start = time.monotonic()
        try:
            while not found:
                remaining = deadline_s - (time.monotonic() - start)
                if remaining <= 0:
                    break
                ch.connection.process_data_events(time_limit=min(0.5, remaining))
        finally:
            try:
                ch.basic_cancel(consumer_tag)
            except Exception:
                pass
        return found[0] if found else None

    def _single_waitfor(
        self,
        uri: str,
        exchange: str,
        routing_key: str,
        body: Optional[bytes],
        properties: Dict[str, Any],
        mandatory: bool,
        timeout_s: Optional[float],
        tls: Optional[Dict[str, Any]],
        waitfor: Dict[str, Any],
    ) -> Tuple[str, Dict[str, str], str]:
        """Publish, then await a response — rpc (correlated reply) or subscribe (bound-queue + Match)."""
        mode = waitfor.get("Mode")
        wf_timeout = waitfor.get("TimeoutSeconds")
        deadline_s = float(wf_timeout) if wf_timeout is not None else (float(timeout_s) if timeout_s else 10.0)

        props_in = dict(properties or {})
        if body and not props_in.get("ContentType"):
            props_in["ContentType"] = "application/json"

        params = pika.URLParameters(uri)
        ssl_opts = self._ssl_options(uri, tls, getattr(params, "host", None))
        if ssl_opts is not None:
            params.ssl_options = ssl_opts

        base_headers: Dict[str, str] = {
            "x-amqp-exchange": exchange or "",
            "x-amqp-routing-key": routing_key or "",
        }

        conn = pika.BlockingConnection(params)
        try:
            ch = conn.channel()

            if mode == "rpc":
                # Exclusive server-named reply queue; correlate by correlation_id.
                reply_q = ch.queue_declare(queue="", exclusive=True).method.queue
                corr_id = str(props_in.get("CorrelationId") or uuid.uuid4())
                props_in["CorrelationId"] = corr_id
                props_in["ReplyTo"] = reply_q
                props = self._build_properties(props_in)
                ch.basic_publish(exchange=exchange or "", routing_key=routing_key or "",
                                 body=body or b"", properties=props, mandatory=bool(mandatory))
                wait_t0 = time.monotonic()
                hit = self._consume_until(
                    ch, reply_q, deadline_s,
                    match=lambda m, p, b: str(getattr(p, "correlation_id", None) or "") == corr_id,
                )
                wait_ms = int(round((time.monotonic() - wait_t0) * 1000))
                if hit is None:
                    headers = dict(base_headers)
                    headers["x-correlation-id"] = corr_id
                    headers["x-amqp-wait-ms"] = str(wait_ms)
                    return "timeout", headers, ""
                _m, p, b = hit
                headers = dict(base_headers)
                headers.update(self._props_to_headers(p))
                headers.setdefault("x-correlation-id", corr_id)
                headers["x-amqp-wait-ms"] = str(wait_ms)
                text = b.decode("utf-8", "replace") if isinstance(b, (bytes, bytearray)) else str(b)
                return "reply", headers, text

            # subscribe: bind a temp queue to WaitFor.Exchange BEFORE publishing the trigger.
            wf_exchange = waitfor.get("Exchange") or ""
            wf_key = waitfor.get("RoutingKey") or ""
            match_cfg = waitfor.get("Match") or []
            temp_q = ch.queue_declare(queue="", exclusive=True).method.queue
            ch.queue_bind(queue=temp_q, exchange=wf_exchange, routing_key=wf_key)

            props = self._build_properties(props_in)  # outgoing message is NOT mutated for subscribe
            ch.basic_publish(exchange=exchange or "", routing_key=routing_key or "",
                             body=body or b"", properties=props, mandatory=bool(mandatory))

            nonmatching = [0]

            def _matches(m, p, b):
                text = b.decode("utf-8", "replace") if isinstance(b, (bytes, bytearray)) else str(b)
                hdrs = self._props_to_headers(p)
                hdrs["x-amqp-routing-key"] = getattr(m, "routing_key", "") or ""
                results = evaluate_expect(match_cfg, "", hdrs, text, 0)
                ok = bool(results) and all(passed for _, passed, _ in results)
                if not ok:
                    nonmatching[0] += 1
                return ok

            wait_t0 = time.monotonic()
            hit = self._consume_until(ch, temp_q, deadline_s, match=_matches)
            wait_ms = int(round((time.monotonic() - wait_t0) * 1000))
            if hit is None:
                headers = dict(base_headers)
                headers["x-amqp-nonmatching-count"] = str(nonmatching[0])
                headers["x-amqp-wait-ms"] = str(wait_ms)
                return "timeout", headers, ""
            m, p, b = hit
            headers = dict(base_headers)
            headers.update(self._props_to_headers(p))
            headers["x-amqp-routing-key"] = getattr(m, "routing_key", "") or ""
            headers["x-amqp-nonmatching-count"] = str(nonmatching[0])
            headers["x-amqp-wait-ms"] = str(wait_ms)
            text = b.decode("utf-8", "replace") if isinstance(b, (bytes, bytearray)) else str(b)
            return "matched", headers, text
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _compute_delay(attempt_idx: int, strategy: str, base: float, mult: float,
                       max_backoff: Optional[float], jitter: Optional[Any]) -> float:
        base = base or 0.0
        mult = mult or 2.0
        if strategy == "fixed":
            delay = base
        else:
            delay = base * (mult ** (attempt_idx - 1))
        if max_backoff is not None:
            delay = min(delay, max_backoff)
        if jitter is True or (isinstance(jitter, str) and jitter.lower() == "full"):
            delay = random.uniform(0, max(delay, 0.0))
        elif isinstance(jitter, str) and jitter.lower() in ("min", "floor", "at_least_base"):
            delay = max(base, random.uniform(0, max(delay, 0.0)))
        return max(0.0, float(delay))

    def publish(
        self,
        *,
        uri: Optional[str],
        exchange: str = "",
        routing_key: str = "",
        body: Optional[bytes] = None,
        properties: Optional[Dict[str, Any]] = None,
        confirm: bool = False,
        mandatory: bool = False,
        timeout_s: Optional[float] = None,
        retry_cfg: Optional[Dict[str, Any]] = None,
        tls: Optional[Dict[str, Any]] = None,
        waitfor: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, Dict[str, str], str, int, str]:
        """Publish one AMQP message (and optionally await a response). See module docstring."""
        log_lines: list[str] = []
        properties = properties or {}

        if not (isinstance(uri, str) and uri.strip()):
            err = ValueError("AMQP broker URI is required (set AMQP.URI or Defaults.AMQP.URI)")
            setattr(err, "request_log", "\n".join(log_lines))
            setattr(err, "attempts_made", 1)
            raise err

        def _do_attempt():
            if waitfor:
                return self._single_waitfor(uri, exchange, routing_key, body, properties, mandatory, timeout_s, tls, waitfor)
            return self._single_publish(uri, exchange, routing_key, body, properties, confirm, mandatory, timeout_s, tls)

        # No retry configured -> single attempt.
        if not retry_cfg:
            status, headers, text = _do_attempt()
            return status, headers, text, 1, ""

        attempts = int(retry_cfg.get("Attempts", 1) or 1)
        if attempts < 1:
            attempts = 1
        strategy = str(retry_cfg.get("BackoffStrategy", "exponential")).lower()
        base = float(retry_cfg.get("BackoffSeconds", 0.0) or 0.0)
        mult = float(retry_cfg.get("Multiplier", 2.0) or 2.0)
        max_backoff = retry_cfg.get("MaxBackoffSeconds")
        max_backoff = float(max_backoff) if max_backoff is not None else None
        max_elapsed = retry_cfg.get("MaxElapsedSeconds")
        max_elapsed = float(max_elapsed) if max_elapsed is not None else None
        jitter = retry_cfg.get("Jitter")
        ron_errors = retry_cfg.get("RetryOnNetworkErrors")
        if ron_errors is None:
            ron_errors = True

        start = time.monotonic()
        for attempt in range(1, attempts + 1):
            try:
                status, headers, text = _do_attempt()
                return status, headers, text, attempt, "\n".join(log_lines)
            except _RETRYABLE_EXCS as e:
                et = type(e).__name__
                if not ron_errors:
                    log_lines.append(f"Retry: attempt {attempt}/{attempts} raised {et}: {e}. RetryOnNetworkErrors disabled; abort.")
                    setattr(e, "request_log", "\n".join(log_lines))
                    setattr(e, "attempts_made", attempt)
                    raise
                log_lines.append(f"Retry: attempt {attempt}/{attempts} raised {et}: {e}. Marked retryable.")
                if attempt >= attempts:
                    log_lines.append(f"Retry: attempts exhausted after {attempts} attempts; raising last error.")
                    setattr(e, "request_log", "\n".join(log_lines))
                    setattr(e, "attempts_made", attempt)
                    raise
                delay = self._compute_delay(attempt, strategy, base, mult, max_backoff, jitter)
                if max_elapsed is not None and (time.monotonic() - start) + delay > max_elapsed:
                    log_lines.append(f"Retry: max elapsed budget {max_elapsed:.3f}s would be exceeded. Aborting retries.")
                    setattr(e, "request_log", "\n".join(log_lines))
                    setattr(e, "attempts_made", attempt)
                    raise
                if delay > 0:
                    log_lines.append(f"Retry: scheduling retry {attempt}/{attempts - 1}; backoff={strategy} -> delay {delay:.3f} s")
                    time.sleep(delay)
                else:
                    log_lines.append("Retry: no delay before next attempt")

        # Unreachable, but keep a defined return.
        return "published", {}, "", attempts, "\n".join(log_lines)

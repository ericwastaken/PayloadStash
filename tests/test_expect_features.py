"""Expect features: retry until Expect passes, typed captures, Defaults.Expect,
collection matchers, same-response references and sequence-level Expect.

Runs as a script or under pytest; a FAIL fails both:
    .venv/bin/python tests/test_expect_features.py
    python -m pytest tests/test_expect_features.py
"""
import functools
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payload_stash.config_schema import validate_config_data, build_resolved_config_dict
from payload_stash.config_utility import resolve_deferred, evaluate_expect, _apply_matcher, resolve_response_path

_results = []
_failed = []


def check(name, cond):
    _results.append(bool(cond))
    if not cond:
        _failed.append(name)
    print(("PASS" if cond else "FAIL"), name)
    return bool(cond)


def gated(fn):
    """Raise AssertionError at the end of a test function if any of its checks failed,
    so pytest reports the function as failed (check() itself only records)."""
    @functools.wraps(fn)
    def wrapper():
        start = len(_failed)
        fn()
        new = _failed[start:]
        if new:
            raise AssertionError("%d check(s) failed: %s" % (len(new), "; ".join(new)))
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rejected(y, needle=None):
    """True when `payloadstash validate` would reject the config (schema check plus resolution),
    and, if given, the message contains needle."""
    try:
        build_resolved_config_dict(validate_config_data(yaml.safe_load(y)))
        return False
    except Exception as e:
        return needle is None or needle in str(e)


def _accepted(y):
    try:
        build_resolved_config_dict(validate_config_data(yaml.safe_load(y)))
        return True
    except Exception as e:
        print("    unexpected validation error:", e)
        return False


def _resolved_req(y, seq=0, i=0):
    cfg = validate_config_data(yaml.safe_load(y))
    r = build_resolved_config_dict(cfg)
    item = r["StashConfig"]["Sequences"][seq]["Requests"][i]
    return next(iter(item.values()))


class _State:
    """Per-server counters the handler reads and writes."""

    def __init__(self):
        self.lock = threading.Lock()
        self.hits = {}
        self.seen = []  # (path, headers dict, parsed body) per request, in arrival order

    def hit(self, path):
        with self.lock:
            self.hits[path] = self.hits.get(path, 0) + 1
            return self.hits[path]


def _make_handler(state, routes):
    """routes: {path: fn(n, req_body) -> (status, body_obj)}; n is the 1-based hit count for path
    and req_body the parsed JSON request body (or None)."""

    class _Handler(BaseHTTPRequestHandler):
        def _serve(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                req_body = json.loads(raw) if raw else None
            except Exception:
                req_body = None
            path = self.path.split("?", 1)[0]
            with state.lock:
                state.seen.append((path, dict(self.headers), req_body))
            fn = routes.get(path)
            if fn is None:
                status, obj = 404, {"error": "no route"}
            else:
                status, obj = fn(state.hit(path), req_body)
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _serve
        do_POST = _serve

        def log_message(self, *a):
            pass

    return _Handler


class _Server:
    def __init__(self, routes):
        self.state = _State()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.state, routes))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _run(config_text, *, cmd="run"):
    """Run the CLI on config_text. Returns (exit_code, combined log text, stdout+stderr)."""
    tmp = Path(tempfile.mkdtemp(prefix="ps-expect-features-"))
    try:
        cfg = tmp / "cfg.yml"
        cfg.write_text(config_text, encoding="utf-8")
        args = [sys.executable, "-c", "from payload_stash.main import main; main()", cmd, str(cfg)]
        if cmd == "run":
            args += ["--out", str(tmp / "out"), "--yes"]
        proc = subprocess.run(args, cwd=str(Path(__file__).resolve().parents[1]),
                              capture_output=True, text=True, timeout=120)
        logs = list((tmp / "out").rglob("*.log")) if cmd == "run" else []
        log_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in logs)
        reports = list((tmp / "out").rglob("*-report.md")) if cmd == "run" else []
        report_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in reports)
        csvs = list((tmp / "out").rglob("*-results.csv")) if cmd == "run" else []
        csv_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in csvs)
        return proc.returncode, log_text, proc.stdout + proc.stderr, report_text, csv_text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


BASE = """
StashConfig:
  Name: ExpectFeatures
  Defaults:
    URLRoot: http://127.0.0.1:{port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10
  Sequences:
    - Name: S
      Type: Sequential
      Requests:
{requests}
"""


def _cfg(port, requests, defaults_extra=""):
    text = BASE.format(port=port, requests=requests)
    if defaults_extra:
        text = text.replace("      TimeoutSeconds: 10\n", "      TimeoutSeconds: 10\n" + defaults_extra, 1)
    return text


# ---------------------------------------------------------------------------
# F1: Retry.RetryOnExpectFailure
# ---------------------------------------------------------------------------

POLL_REQ = """        - Poll:
            Method: GET
            URLPath: /ready
            Retry:
              Attempts: {attempts}
              BackoffStrategy: fixed
              BackoffSeconds: 0.05
{extra}
            Expect:
              - status: 200
              - body.ready: true
"""


@gated
def test_retry_on_expect_failure():
    print("\n--- F1: RetryOnExpectFailure ---")

    # Becomes ready on the 3rd call.
    srv = _Server({"/ready": lambda n, b: (200, {"ready": n >= 3})})
    try:
        req = POLL_REQ.format(attempts=10, extra="              RetryOnExpectFailure: true")
        code, log, out, report, csv_text = _run(_cfg(srv.port, req))
        check("F1 polls until Expect passes: exit 0", code == 0)
        check("F1 polls until Expect passes: exactly 3 calls", srv.state.hits.get("/ready") == 3)
        check("F1 retry reason names the Expect failure", "due to Expect failed (1 of 2 assertions)" in log)
        check("F1 final Expect is reported as passed", "✓ body.ready equals True" in log and "✗" not in log)
        check("F1 CSV attempts counts every attempt", ",3,2,0" in csv_text)
    finally:
        srv.close()

    # Never ready: attempts run out, the last response's Expect failure is reported.
    srv = _Server({"/ready": lambda n, b: (200, {"ready": False})})
    try:
        req = POLL_REQ.format(attempts=4, extra="              RetryOnExpectFailure: true")
        code, log, out, report, csv_text = _run(_cfg(srv.port, req))
        check("F1 exhausted attempts: exit 1", code == 1)
        check("F1 exhausted attempts: used every attempt", srv.state.hits.get("/ready") == 4)
        check("F1 exhausted attempts: failure reported", "✗ body.ready equals True" in log)
    finally:
        srv.close()

    # Never ready with a time budget: stops at MaxElapsedSeconds.
    srv = _Server({"/ready": lambda n, b: (200, {"ready": False})})
    try:
        req = POLL_REQ.format(attempts=1000, extra="              MaxElapsedSeconds: 0.3\n              RetryOnExpectFailure: true")
        code, log, out, report, csv_text = _run(_cfg(srv.port, req))
        hits = srv.state.hits.get("/ready", 0)
        check("F1 MaxElapsedSeconds: exit 1", code == 1)
        check("F1 MaxElapsedSeconds: stopped early (%d calls)" % hits, 2 <= hits <= 10)
        check("F1 MaxElapsedSeconds: budget logged", "max elapsed budget" in log)
    finally:
        srv.close()

    # Status retries still work alongside Expect retries, within one attempt budget.
    srv = _Server({"/ready": lambda n, b: (503, {}) if n == 1 else (200, {"ready": n >= 3})})
    try:
        req = POLL_REQ.format(attempts=10, extra="              RetryOnExpectFailure: true")
        code, log, out, report, csv_text = _run(_cfg(srv.port, req))
        check("F1 status + Expect retries share the loop: exit 0", code == 0)
        check("F1 status + Expect retries share the loop: 3 calls", srv.state.hits.get("/ready") == 3)
    finally:
        srv.close()

    # Without the flag, a failed Expect is not retried (unchanged behaviour).
    srv = _Server({"/ready": lambda n, b: (200, {"ready": n >= 3})})
    try:
        req = POLL_REQ.format(attempts=10, extra="")
        code, log, out, report, csv_text = _run(_cfg(srv.port, req))
        check("F1 flag absent: single call", srv.state.hits.get("/ready") == 1)
        check("F1 flag absent: exit 1", code == 1)
    finally:
        srv.close()

    # Request-time values are re-resolved for every F1 attempt; resolve-time values are not.
    fresh_req = """        - Poll:
            Method: POST
            URLPath: /ready
            Headers:
              timestamp: { $timestamp: { format: epoch_ms, when: request } }
            Body:
              sentAt: { $timestamp: { format: epoch_ms, when: request } }
              fixedAt: { $timestamp: { format: epoch_ms } }
            Retry:
              Attempts: 5
              BackoffStrategy: fixed
              BackoffSeconds: 0.05
{extra}
            Expect:
              - body.ready: true
"""
    srv = _Server({"/ready": lambda n, b: (200, {"ready": n >= 3})})
    try:
        code, log, out, report, csv_text = _run(_cfg(srv.port, fresh_req.replace("{extra}", "              RetryOnExpectFailure: true")))
        bodies = [b for _, _, b in srv.state.seen]
        hdr_ts = [{k.lower(): v for k, v in h.items()}.get("timestamp") for _, h, _ in srv.state.seen]
        check("F1 fresh values: exit 0 after 3 calls", code == 0 and len(bodies) == 3)
        check("F1 fresh values: request-time body value differs per attempt",
              len({b["sentAt"] for b in bodies}) == 3)
        check("F1 fresh values: request-time header differs per attempt", len(set(hdr_ts)) == 3)
        check("F1 fresh values: resolve-time value is the same every attempt",
              len({b["fixedAt"] for b in bodies}) == 1)
        check("F1 fresh values: re-resolution is logged", log.count("Retry: re-resolved request-time values") == 2)
    finally:
        srv.close()

    # Status retries without the flag re-send the first request unchanged (1.2.0 behaviour).
    srv = _Server({"/ready": lambda n, b: (503, {}) if n < 3 else (200, {"ready": True})})
    try:
        code, log, out, report, csv_text = _run(_cfg(srv.port, fresh_req.replace("{extra}\n", "")))
        bodies = [b for _, _, b in srv.state.seen]
        check("F1 status retry without the flag: 3 calls", code == 0 and len(bodies) == 3)
        check("F1 status retry without the flag: body re-sent unchanged",
              len({json.dumps(b, sort_keys=True) for b in bodies}) == 1)
    finally:
        srv.close()

    # Validation.
    no_expect = _cfg(1, """        - Poll:
            Method: GET
            URLPath: /ready
            Retry:
              Attempts: 3
              BackoffStrategy: fixed
              BackoffSeconds: 0
              RetryOnExpectFailure: true
""")
    check("F1 validate: request flag without Expect is rejected",
          _rejected(no_expect, "RetryOnExpectFailure requires an Expect list"))

    amqp = _cfg(1, """        - Pub:
            Transport: amqp
            AMQP:
              URI: amqp://guest:guest@127.0.0.1:5672/
              RoutingKey: q
            Retry:
              Attempts: 3
              BackoffStrategy: fixed
              BackoffSeconds: 0
              RetryOnExpectFailure: true
            Expect:
              - status: ack
""")
    check("F1 validate: request flag on AMQP is rejected",
          _rejected(amqp, "RetryOnExpectFailure is supported for HTTP requests only"))

    inherited = _cfg(1, """        - Pub:
            Transport: amqp
            AMQP:
              URI: amqp://guest:guest@127.0.0.1:5672/
              RoutingKey: q
        - Plain:
            Method: GET
            URLPath: /x
""", defaults_extra="""    Retry:
      Attempts: 3
      BackoffStrategy: fixed
      BackoffSeconds: 0
      RetryOnExpectFailure: true
""")
    check("F1 validate: flag inherited from Defaults is accepted for AMQP / no-Expect requests",
          _accepted(inherited))

    bad_type = _cfg(1, POLL_REQ.format(attempts=3, extra="              RetryOnExpectFailure: [1]"))
    check("F1 validate: non-boolean flag is rejected", _rejected(bad_type, "RetryOnExpectFailure"))

    ok = _cfg(1, POLL_REQ.format(attempts=3, extra="              RetryOnExpectFailure: true"))
    check("F1 resolved config carries the flag",
          _resolved_req(ok).get("Retry", {}).get("RetryOnExpectFailure") is True)


# ---------------------------------------------------------------------------
# F2: { $captured: KEY } typed capture references
# ---------------------------------------------------------------------------

@gated
def test_typed_captures():
    print("\n--- F2: $captured ---")

    y = _cfg(1, """        - R:
            Method: POST
            URLPath: /x
            Capture:
              team: body.team
              points: body.points
            Body:
              team: { $captured: team }
            Expect:
              - body.points: { equals: { $captured: points } }
              - body.label: { matches: { $pattern: "^${captured:label}$" } }
""")
    r = _resolved_req(y)
    check("F2 resolves to a deferred capture marker",
          r["Expect"][0]["body.points"]["equals"] == {"$deferred": {"captured": "points"}})
    check("F2 Body marker", r["Body"]["team"] == {"$deferred": {"captured": "team"}})

    caps = {"points": 7, "team": ["u1", "u2"], "obj": {"a": 1}, "flag": False}
    check("F2 number keeps its type", resolve_deferred({"$deferred": {"captured": "points"}}, captures=caps) == 7)
    check("F2 list keeps its type", resolve_deferred({"$deferred": {"captured": "team"}}, captures=caps) == ["u1", "u2"])
    check("F2 object keeps its type", resolve_deferred({"$deferred": {"captured": "obj"}}, captures=caps) == {"a": 1})
    check("F2 false is kept", resolve_deferred({"$deferred": {"captured": "flag"}}, captures=caps) is False)
    check("F2 missing capture is null", resolve_deferred({"$deferred": {"captured": "nope"}}, captures=caps) is None)
    check("F2 nested inside a list", resolve_deferred([{"$deferred": {"captured": "points"}}], captures=caps) == [7])
    check("F2 ${captured:KEY} is still a string",
          resolve_deferred({"$deferred": {"pattern": {"template": "${captured:points}", "sets": {}}}}, captures=caps) == "7")

    check("F2 validate: empty key rejected",
          _rejected(y.replace("{ $captured: points }", '{ $captured: "" }'), "$captured"))
    check("F2 validate: non-string key rejected",
          _rejected(y.replace("{ $captured: points }", "{ $captured: [points] }"), "$captured"))

    # End to end: capture typed values, compare and send them back typed.
    def echo(n, b):
        return 200, {"echo": b, "points": 7, "team": ["u1", "u2"]}
    srv = _Server({"/first": lambda n, b: (200, {"points": 7, "team": ["u1", "u2"], "meta": {"tier": 3}}),
                   "/echo": echo})
    try:
        reqs = """        - First:
            Method: GET
            URLPath: /first
            Capture:
              points: body.points
              team: body.team
              meta: body.meta
        - Second:
            Method: POST
            URLPath: /echo
            Body:
              team: { $captured: team }
              points: { $captured: points }
            Expect:
              - body.points: { equals: { $captured: points } }
              - body.team: { equals: { $captured: team } }
              - body.echo.team: { equals: { $captured: team } }
              - body.echo.points: { type: integer }
              - body.points: { lte: { $captured: points } }
"""
        code, log, out, report, csv_text = _run(_cfg(srv.port, reqs))
        check("F2 end to end: exit 0", code == 0)
        check("F2 end to end: all assertions passed", log.count("✓") == 5 and "✗" not in log)
    finally:
        srv.close()

    srv = _Server({"/first": lambda n, b: (200, {"points": 7})})
    try:
        reqs = """        - First:
            Method: GET
            URLPath: /first
            Expect:
              - body.points: { equals: { $captured: neverCaptured } }
"""
        code, log, out, report, csv_text = _run(_cfg(srv.port, reqs))
        check("F2 unknown capture name fails the run before any request",
              code != 0 and "neverCaptured" in out and srv.state.hits.get("/first") is None)
    finally:
        srv.close()

    unknown = """        - First:
            Method: GET
            URLPath: /first
            Capture:
              points: body.points
        - Second:
            Method: POST
            URLPath: /echo
            Body:
              n: { $captured: pionts }
"""
    check("F2 validate: unknown $captured name in Body is rejected, naming it",
          _rejected(_cfg(1, unknown), "pionts"))
    check("F2 validate: unknown $captured name in Expect is rejected",
          _rejected(_cfg(1, unknown.replace("Body:\n              n: { $captured: pionts }",
                                            "Expect:\n              - body.n: { equals: { $captured: nope } }")), "nope"))
    check("F2 validate: a name captured by any request is accepted",
          _accepted(_cfg(1, unknown.replace("pionts", "points"))))
    check("F2 validate: ${captured:KEY} strings are not checked (unchanged)",
          _accepted(_cfg(1, unknown.replace("{ $captured: pionts }", "{ $pattern: 'x${captured:nope}' }"))))


# ---------------------------------------------------------------------------
# F3: Defaults.Expect and SkipDefaultExpect
# ---------------------------------------------------------------------------

DEFAULT_EXPECT = """    Expect:
      - status: 200
      - body.ok: true
"""


@gated
def test_defaults_expect():
    print("\n--- F3: Defaults.Expect ---")

    y = _cfg(1, """        - Plain:
            Method: GET
            URLPath: /a
        - Own:
            Method: GET
            URLPath: /b
            Expect:
              - body.n: 2
        - Skipped:
            Method: GET
            URLPath: /c
            SkipDefaultExpect: true
            Expect:
              - status: 404
        - SkippedNoOwn:
            Method: GET
            URLPath: /d
            SkipDefaultExpect: true
        - Pub:
            Transport: amqp
            AMQP:
              URI: amqp://guest:guest@127.0.0.1:5672/
              RoutingKey: q
""", defaults_extra=DEFAULT_EXPECT)
    check("F3 request without Expect inherits Defaults.Expect",
          _resolved_req(y, i=0).get("Expect") == [{"status": 200}, {"body.ok": True}])
    check("F3 Defaults.Expect runs before the request's own",
          _resolved_req(y, i=1).get("Expect") == [{"status": 200}, {"body.ok": True}, {"body.n": 2}])
    check("F3 SkipDefaultExpect keeps only the request's own",
          _resolved_req(y, i=2).get("Expect") == [{"status": 404}])
    check("F3 SkipDefaultExpect with no own Expect leaves none",
          "Expect" not in _resolved_req(y, i=3))
    check("F3 AMQP requests inherit Defaults.Expect too",
          _resolved_req(y, i=4).get("Expect") == [{"status": 200}, {"body.ok": True}])
    check("F3 SkipDefaultExpect is not copied into the resolved request",
          "SkipDefaultExpect" not in _resolved_req(y, i=2))

    no_defaults = _cfg(1, """        - Own:
            Method: GET
            URLPath: /b
            Expect:
              - body.n: 2
        - Empty:
            Method: GET
            URLPath: /b
            Expect: []
""")
    check("F3 no Defaults.Expect: request Expect unchanged", _resolved_req(no_defaults).get("Expect") == [{"body.n": 2}])
    check("F3 no Defaults.Expect: explicit empty list unchanged", _resolved_req(no_defaults, i=1).get("Expect") == [])

    check("F3 validate: Defaults.Expect must be a list",
          _rejected(_cfg(1, """        - Plain:
            Method: GET
            URLPath: /a
""", defaults_extra="    Expect: { status: 200 }\n"), "Expect"))
    check("F3 validate: SkipDefaultExpect must be boolean",
          _rejected(y.replace("SkipDefaultExpect: true", "SkipDefaultExpect: [x]", 1), "SkipDefaultExpect"))

    # RetryOnExpectFailure is satisfied by assertions inherited from Defaults.Expect ...
    poll = _cfg(1, """        - Poll:
            Method: GET
            URLPath: /ready
            Retry:
              Attempts: 3
              BackoffStrategy: fixed
              BackoffSeconds: 0
              RetryOnExpectFailure: true
""", defaults_extra=DEFAULT_EXPECT)
    check("F3 + F1: inherited assertions satisfy RetryOnExpectFailure", _accepted(poll))
    # ... but not when the request opts out of them.
    check("F3 + F1: opted-out request with no own Expect is rejected",
          _rejected(poll.replace("URLPath: /ready\n", "URLPath: /ready\n            SkipDefaultExpect: true\n"),
                    "RetryOnExpectFailure requires an Expect list"))

    # End to end: Defaults.Expect is evaluated and counted for a request with no Expect.
    srv = _Server({"/a": lambda n, b: (200, {"ok": True}), "/b": lambda n, b: (200, {"ok": False}),
                   "/c": lambda n, b: (404, {})})
    try:
        reqs = """        - Good:
            Method: GET
            URLPath: /a
        - Missing:
            Method: GET
            URLPath: /c
            SkipDefaultExpect: true
            Expect:
              - status: 404
"""
        code, log, out, report, csv_text = _run(_cfg(srv.port, reqs, defaults_extra=DEFAULT_EXPECT))
        check("F3 end to end: exit 0", code == 0)
        check("F3 end to end: inherited assertions evaluated", log.count("✓") == 3 and "✗" not in log)
        check("F3 end to end: CSV counts inherited assertions", ",2,0" in csv_text)

        reqs_bad = """        - Bad:
            Method: GET
            URLPath: /b
"""
        code, log, out, report, csv_text = _run(_cfg(srv.port, reqs_bad, defaults_extra=DEFAULT_EXPECT))
        check("F3 end to end: inherited failure fails the run", code == 1 and "✗ body.ok equals True" in log)
    finally:
        srv.close()


# ---------------------------------------------------------------------------
# F4: collection matchers and ::count on zero matches
# ---------------------------------------------------------------------------

@gated
def test_collection_matchers():
    print("\n--- F4: collection matchers, ::count ---")

    def m(k, a, e):
        return _apply_matcher(k, a, e)

    check("F4 unique: distinct list", m("unique", ["a", "b", "c"], True)[0])
    check("F4 unique: duplicate fails", not m("unique", ["a", "b", "a"], True)[0])
    check("F4 unique: duplicate detail names it", "duplicates: ['a']" in m("unique", ["a", "b", "a"], True)[1])
    check("F4 unique: false asserts a duplicate exists", m("unique", ["a", "a"], False)[0])
    check("F4 unique: objects compared by value", not m("unique", [{"x": 1, "y": 2}, {"y": 2, "x": 1}], True)[0])
    check("F4 unique: empty list is unique", m("unique", [], True)[0])
    check("F4 unique: non-list fails", not m("unique", "abc", True)[0])

    check("F4 setEquals: any order", m("setEquals", ["b", "a"], ["a", "b"])[0])
    check("F4 setEquals: ignores repeats", m("setEquals", ["a", "a", "b"], ["b", "a"])[0])
    check("F4 setEquals: missing element fails", not m("setEquals", ["a"], ["a", "b"])[0])
    check("F4 setEquals: extra element fails", not m("setEquals", ["a", "b", "c"], ["a", "b"])[0])
    detail = m("setEquals", ["a", "c"], ["a", "b"])[1]
    check("F4 setEquals: detail lists missing and unexpected", "missing: ['b']" in detail and "unexpected: ['c']" in detail)
    check("F4 setEquals: objects", m("setEquals", [{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])[0])
    check("F4 setEquals: non-list fails", not m("setEquals", None, ["a"])[0])

    check("F4 containsAll: subset passes", m("containsAll", ["a", "b", "c"], ["c", "a"])[0])
    check("F4 containsAll: missing fails", not m("containsAll", ["a"], ["a", "z"])[0])
    check("F4 containsAll: detail lists missing", "missing: ['z']" in m("containsAll", ["a"], ["a", "z"])[1])
    check("F4 containsAll: empty expected passes", m("containsAll", ["a"], [])[0])

    check("F4 keysEqual: any order", m("keysEqual", {"b": 1, "a": 2}, ["a", "b"])[0])
    check("F4 keysEqual: extra key fails", not m("keysEqual", {"a": 1, "b": 2, "c": 3}, ["a", "b"])[0])
    check("F4 keysEqual: missing key fails", not m("keysEqual", {"a": 1}, ["a", "b"])[0])
    check("F4 keysEqual: non-object fails", not m("keysEqual", ["a", "b"], ["a", "b"])[0])

    body = json.dumps({"items": [{"id": "a", "class": "x"}, {"id": "b", "class": "x"}], "empty": []})
    check("F4 ::count of matches", resolve_response_path({"$jsonpath": "$.items[?(@.class=='x')]::count"}, 200, {}, body, 1) == 2)
    check("F4 ::count of zero matches is 0", resolve_response_path({"$jsonpath": "$.items[?(@.class=='y')]::count"}, 200, {}, body, 1) == 0)
    check("F4 ::count of an empty array is 0", resolve_response_path({"$jsonpath": "$.empty[*]::count"}, 200, {}, body, 1) == 0)
    check("F4 ::sum of zero matches is still null", resolve_response_path({"$jsonpath": "$.nope[*]::sum"}, 200, {}, body, 1) is None)
    check("F4 ::first of zero matches is still null", resolve_response_path({"$jsonpath": "$.nope[*]::first"}, 200, {}, body, 1) is None)
    check("F4 no aggregation, zero matches is still null", resolve_response_path({"$jsonpath": "$.nope"}, 200, {}, body, 1) is None)

    res = evaluate_expect([
        {"$.items[*].id": {"unique": True, "setEquals": ["b", "a"], "containsAll": ["a"]}},
        {"$.items[0]": {"keysEqual": ["id", "class"]}},
        {"$.items[?(@.class=='y')]::count": {"equals": 0}},
    ], 200, {}, body, 1)
    check("F4 matchers through evaluate_expect", len(res) == 5 and all(r[1] for r in res))

    # List matchers on a wildcard/filter path: one match is a one-element list, none is an empty list.
    one = json.dumps({"items": [{"id": "a", "tags": ["t1", "t2"]}], "arr": ["a"], "none": []})

    def ev(path, spec):
        return evaluate_expect([{path: spec}], 200, {}, one, 1)

    def ok(path, spec):
        r = ev(path, spec)
        return len(r) == len(spec) and all(x[1] for x in r)

    check("F4 one match: unique passes", ok("$.items[*].id", {"unique": True}))
    check("F4 one match: unique false fails", not ok("$.items[*].id", {"unique": False}))
    check("F4 one match: setEquals one-element list", ok("$.items[*].id", {"setEquals": ["a"]}))
    check("F4 one match: setEquals wrong element fails", not ok("$.items[*].id", {"setEquals": ["b"]}))
    check("F4 one match: containsAll", ok("$.items[*].id", {"containsAll": ["a"]}))
    check("F4 one match (filter): setEquals", ok("$.items[?(@.id=='a')].id", {"setEquals": ["a"]}))
    check("F4 one match whose value is a list stays one element",
          ok("$.items[*].tags", {"setEquals": [["t1", "t2"]]}))
    check("F4 zero matches: setEquals []", ok("$.items[?(@.id=='z')].id", {"setEquals": []}))
    check("F4 zero matches: unique passes", ok("$.none[*]", {"unique": True}))
    check("F4 zero matches: containsAll [] passes", ok("$.nope[*].id", {"containsAll": []}))
    check("F4 zero matches: containsAll [x] fails", not ok("$.nope[*].id", {"containsAll": ["x"]}))
    check("F4 path to the array itself is still the array", ok("$.arr", {"setEquals": ["a"]}))
    check("F4 path to a nested array is the array", ok("$.items[0].tags", {"setEquals": ["t2", "t1"]}))
    check("F4 singular path to a missing key: list matcher still fails",
          not ok("$.missing", {"setEquals": []}))
    check("F4 singular path to a non-list: list matcher still fails",
          not ok("$.items[0].id", {"setEquals": ["a"]}))
    check("F4 one match: expected { $jsonpath } is listed too",
          ok("$.items[*].id", {"setEquals": {"$jsonpath": "$.arr[*]"}}))
    check("F4 zero matches: expected { $jsonpath } is an empty list",
          ok("$.none[*]", {"setEquals": {"$jsonpath": "$.nope[*]"}}))

    # Non-list matchers keep the 1.2.0 shapes: a scalar for one match, null for none.
    check("F4 one match: equals still sees the scalar", ok("$.items[*].id", {"equals": "a"}))
    check("F4 zero matches: exists false still passes", ok("$.items[?(@.id=='z')].id", {"exists": False}))
    check("F4 zero matches: equals null still passes", ok("$.nope[*].id", {"equals": None}))
    check("F4 one match: ::count still 1", ok("$.items[*].id::count", {"equals": 1}))
    check("F4 mixed matchers on one path", ok("$.items[*].id", {"equals": "a", "setEquals": ["a"], "unique": True}))

    base = """        - R:
            Method: GET
            URLPath: /x
            Capture:
              k: body.k
            Expect:
              - body.items: {{ {m} }}
"""
    for spec, needle in [("unique: [1]", "unique expects true or false"),
                         ("setEquals: a", "setEquals expects a list"),
                         ("containsAll: 3", "containsAll expects a list"),
                         ("keysEqual: [1, 2]", "keysEqual expects a list of strings")]:
        check("F4 validate rejects " + spec, _rejected(_cfg(1, base.format(m=spec)), needle))
    for spec in ("unique: true", "setEquals: [a]", "setEquals: { $captured: k }", "containsAll: []",
                 "keysEqual: [a, b]", "keysEqual: { $captured: k }"):
        check("F4 validate accepts " + spec, _accepted(_cfg(1, base.format(m=spec))))
    check("F4 validate checks Defaults.Expect too",
          _rejected(_cfg(1, base.format(m="unique: true"), defaults_extra="    Expect:\n      - body.x: { setEquals: a }\n"),
                    "setEquals expects a list"))


# ---------------------------------------------------------------------------
# F5: { $jsonpath: EXPR } as expected value, resolved against the same response
# ---------------------------------------------------------------------------

@gated
def test_same_response_reference():
    print("\n--- F5: same-response $jsonpath ---")
    body = json.dumps({"items": [{"amount": 5}, {"amount": 7}], "total": 12, "lead": "u1",
                       "order": ["u1", "u2"], "team": ["u2"], "bad": 11})
    res = evaluate_expect([
        {"body.total": {"equals": {"$jsonpath": "$.items[*].amount::sum"}}},
        {"body.lead": {"equals": {"$jsonpath": "$.order[0]"}}},
        {"body.order": {"containsAll": {"$jsonpath": "$.team"}}},
        {"body.lead": {"notIn": {"$jsonpath": "$.team"}}},
        {"$.items[*]::count": {"lte": {"$jsonpath": "$.order[*]::count"}}},
    ], 200, {}, body, 1)
    check("F5 references pass", len(res) == 5 and all(r[1] for r in res))

    res = evaluate_expect([{"body.bad": {"equals": {"$jsonpath": "$.items[*].amount::sum"}}}], 200, {}, body, 1)
    check("F5 mismatch fails", len(res) == 1 and not res[0][1])
    check("F5 failure detail shows both sides",
          "actual: 11" in res[0][2] and "expected ($.items[*].amount::sum): 12" in res[0][2])

    res = evaluate_expect([{"body.total": {"equals": {"$jsonpath": "$.nothing"}}}], 200, {}, body, 1)
    check("F5 reference with no match resolves to null", not res[0][1] and "expected ($.nothing): None" in res[0][2])

    base = """        - R:
            Method: GET
            URLPath: /x
            Expect:
              - body.a: {{ equals: {v} }}
"""
    check("F5 resolved config keeps the reference",
          _resolved_req(_cfg(1, base.format(v='{ $jsonpath: "$.b" }')))["Expect"][0]["body.a"]["equals"] == {"$jsonpath": "$.b"})
    check("F5 validate: non-string expression rejected",
          _rejected(_cfg(1, base.format(v="{ $jsonpath: [1] }")), "$jsonpath expects a JSONPath string"))
    check("F5 validate: unparseable expression rejected",
          _rejected(_cfg(1, base.format(v='{ $jsonpath: "$.[[" }')), "$jsonpath"))

    srv = _Server({"/x": lambda n, b: (200, {"a": 3, "b": 3})})
    try:
        code, log, out, report, csv_text = _run(_cfg(srv.port, base.format(v='{ $jsonpath: "$.b" }')))
        check("F5 end to end: exit 0", code == 0 and "✗" not in log)
    finally:
        srv.close()


# ---------------------------------------------------------------------------
# F6: Sequence-level Expect
# ---------------------------------------------------------------------------

SEQ_CFG = """
StashConfig:
  Name: SeqExpect
  Defaults:
    URLRoot: http://127.0.0.1:{port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10
  Sequences:
    - Name: Pairing
      Type: Concurrent
      ConcurrencyLimit: 4
      Requests:
        - P1: {{ Method: POST, URLPath: /pair, Body: {{ i: 1 }} }}
        - P2: {{ Method: POST, URLPath: /pair, Body: {{ i: 2 }} }}
        - P3: {{ Method: POST, URLPath: /pair, Body: {{ i: 3 }} }}
        - P4: {{ Method: POST, URLPath: /pair, Body: {{ i: 4 }} }}
      Expect:
        - "$.requests[?(@.body.merge.status=='merged')]::count": {{ equals: {merged} }}
        - "$.requests[*].status": {{ setEquals: [200] }}
        - "$.requests[*].key": {{ setEquals: [P1, P2, P3, P4] }}
    - Name: Points
      Type: Sequential
      Requests:
        - Before:
            Method: GET
            URLPath: /points
            Capture:
              before: body.points
        - After:
            Method: GET
            URLPath: /points
            Capture:
              after: body.points
      Expect:
        - "$.captured.after": {{ gt: {{ $captured: before }} }}
        - "$.requests[0].body.points": {{ equals: {{ $captured: before }} }}
"""


@gated
def test_sequence_expect():
    print("\n--- F6: sequence Expect ---")

    def pair(n, b):
        i = (b or {}).get("i")
        return 200, {"merge": {"status": "merged" if i == 2 else "pairedToAnotherMobile"}}

    srv = _Server({"/pair": pair, "/points": lambda n, b: (200, {"points": n * 10})})
    try:
        code, log, out, report, csv_text = _run(SEQ_CFG.format(port=srv.port, merged=1))
        check("F6 passing sequence Expect: exit 0", code == 0)
        check("F6 passing sequence Expect: all assertions shown",
              log.count("✓") == 5 and "✗" not in log and "Sequence Expect:" in log)
        check("F6 report has a sequence entry", "Pairing (sequence)" in report and "Points (sequence)" in report)
        check("F6 CSV has a sequence row", "(sequence)" in csv_text and ",3,0" in csv_text)

        code, log, out, report, csv_text = _run(SEQ_CFG.format(port=srv.port, merged=2))
        check("F6 failing sequence Expect: exit 1", code == 1)
        check("F6 failing sequence Expect: failure shown with actual",
              "✗ $.requests[?(@.body.merge.status=='merged')]::count equals 2" in log and "actual: 1" in log)
    finally:
        srv.close()

    y = SEQ_CFG.format(port=1, merged=1)
    r = build_resolved_config_dict(validate_config_data(yaml.safe_load(y)))
    seq = r["StashConfig"]["Sequences"][1]
    check("F6 resolved config carries the sequence Expect",
          seq.get("Expect", [None])[0] == {"$.captured.after": {"gt": {"$deferred": {"captured": "before"}}}})
    check("F6 validate: non-JSONPath path rejected",
          _rejected(y.replace('"$.captured.after"', "captured.after"), "Sequence Expect paths are JSONPath"))
    check("F6 validate: collection matcher shape checked",
          _rejected(y.replace("setEquals: [200]", "setEquals: 200"), "setEquals expects a list"))

    tmp = Path(tempfile.mkdtemp(prefix="ps-seq-dry-"))
    try:
        cfg = tmp / "c.yml"
        cfg.write_text(y, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-c", "from payload_stash.main import main; main()", "run", str(cfg),
                               "--out", str(tmp / "out"), "--yes", "--dry-run"],
                              cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=60)
        logs = "\n".join(p.read_text(encoding="utf-8") for p in (tmp / "out").rglob("*.log"))
        check("F6 dry run skips the sequence Expect", proc.returncode == 0 and "DRY-RUN: sequence Expect skipped" in logs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run():
    errors = []
    for t in (test_retry_on_expect_failure, test_typed_captures, test_defaults_expect,
              test_collection_matchers, test_same_response_reference, test_sequence_expect):
        try:
            t()
        except AssertionError:
            pass  # already recorded in _failed
        except Exception as e:  # a crash in a test function is a failure, not a skip
            errors.append("%s: %r" % (t.__name__, e))
            print("ERROR", t.__name__, repr(e))
    total, passed = len(_results), sum(_results)
    ok = passed == total and not errors
    print("\n%d/%d passed — %s" % (passed, total, "ALL GREEN" if ok else "RED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run()

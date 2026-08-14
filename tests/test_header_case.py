"""Response header lookups must be case-insensitive (RFC 9110).

urllib3 preserves the casing the server sent, so `headers.ETag` / `headers.etag` /
`headers.ETAG` all have to resolve to the same value in Capture and Expect.

Run:  python tests/test_header_case.py
"""
import sys, json, threading, subprocess, tempfile, shutil
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from payload_stash.config_utility import resolve_response_path, evaluate_expect
from payload_stash.utility import CaseInsensitiveDict, yaml_to_string

_results = []


def check(name, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), name)
    return bool(cond)


# Mimics what request_manager builds from urllib3: original server casing preserved.
MIXED = CaseInsensitiveDict({"ETag": 'W/"abc-def"', "Content-Type": "application/json"})
LOWER = CaseInsensitiveDict({"ipb-servertimeepochms": "1723500000000"})


def run():
    # --- unit: mixed-case stored key, queried every which way ---
    for query in ("headers.ETag", "headers.etag", "headers.ETAG", "headers.eTaG"):
        check(query, resolve_response_path(query, 200, MIXED, "{}", 5) == 'W/"abc-def"')
    check("headers.content-type",
          resolve_response_path("headers.content-type", 200, MIXED, "{}", 5) == "application/json")

    # --- unit: lowercase stored key still resolves (regression guard) ---
    check("lowercase stored, lowercase query",
          resolve_response_path("headers.ipb-servertimeepochms", 200, LOWER, "{}", 5) == "1723500000000")
    check("lowercase stored, mixed query",
          resolve_response_path("headers.IPB-ServerTimeEpochMs", 200, LOWER, "{}", 5) == "1723500000000")

    # --- unit: a plain dict (AMQP Match headers, older callers) folds too ---
    check("plain dict mixed-case",
          resolve_response_path("headers.etag", 200, {"ETag": "xyz"}, "{}", 5) == "xyz")
    check("absent header is None",
          resolve_response_path("headers.nope", 200, MIXED, "{}", 5) is None)

    # --- unit: Expect matchers over mixed-case headers ---
    res = evaluate_expect([
        {"headers.etag": {"exists": True}},
        {"headers.ETag": {"exists": True}},
        {"headers.ETAG": {"equals": 'W/"abc-def"'}},
        {"headers.missing-one": {"exists": False}},
    ], 200, MIXED, "{}", 5)
    for label, passed, _detail in res:
        check("expect " + label, passed)

    # --- unit: the mapping itself ---
    d = CaseInsensitiveDict({"ETag": "v1"})
    check("mapping get", d.get("etag") == "v1" and d.get("ETAG") == "v1")
    check("mapping contains", "etag" in d and "ETag" in d)
    check("mapping preserves casing for display", list(d.keys()) == ["ETag"])
    d["etag"] = "v2"
    check("case-differing reassign is one entry", list(d.items()) == [("etag", "v2")])
    check("mapping is yaml-dumpable", yaml_to_string(CaseInsensitiveDict({"ETag": "v1"})).strip() == "ETag: v1")
    check("mapping is json-dumpable", json.loads(json.dumps(CaseInsensitiveDict({"ETag": "v1"}))) == {"ETag": "v1"})

    # --- integration: Capture headers.ETag, replay it as a request header ---
    check("integration round-trip", _integration())

    total, passed = len(_results), sum(_results)
    print("\n%d/%d passed — %s" % (total and passed, total, "ALL GREEN" if passed == total else "RED"))
    sys.exit(0 if passed == total else 1)


class _Handler(BaseHTTPRequestHandler):
    """GET /etag answers with a mixed-case ETag; POST /echo mirrors request headers as JSON."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("ETag", 'W/"abc-def"')
        self.send_header("Content-Type", "application/json")
        body = b"{}"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        seen = {k.lower(): v for k, v in self.headers.items()}
        body = json.dumps({"seenIfMatch": seen.get("if-match")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


CONFIG = """
StashConfig:
  Name: HeaderCaseRoundTrip
  Defaults:
    URLRoot: http://127.0.0.1:{port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 10

  Sequences:
    - Name: HeaderCase
      Type: Sequential
      Requests:
        - GetEtag:
            Method: GET
            URLPath: /etag
            Capture:
              myEtag: headers.ETag
            Expect:
              - status: 200
              - headers.etag: {{ exists: true }}
              - headers.ETag: {{ exists: true }}
              - headers.ETAG: {{ equals: 'W/"abc-def"' }}

        - ReplayEtag:
            Method: POST
            URLPath: /echo
            Headers:
              If-Match: {{ $pattern: "${{captured:myEtag}}" }}
            Body:
              ping: 1
            Expect:
              - status: 200
              - body.seenIfMatch: {{ equals: 'W/"abc-def"' }}
"""


def _integration() -> bool:
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = Path(tempfile.mkdtemp(prefix="ps-header-case-"))
    try:
        cfg = tmp / "header-case.yml"
        cfg.write_text(CONFIG.format(port=port), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-c", "from payload_stash.main import main; main()",
             "run", str(cfg), "--out", str(tmp / "out"), "--yes"],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout[-3000:])
            print(proc.stderr[-3000:], file=sys.stderr)
            return False
        # Every Expect in the config must have passed, and the captured ETag must have gone
        # back out as the If-Match request header.
        logs = list((tmp / "out").rglob("*.log"))
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in logs)
        if "✗" in text or 'If-Match: W/"abc-def"' not in text:
            print(text[-3000:])
            return False
        return text.count("✓") >= 6
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()

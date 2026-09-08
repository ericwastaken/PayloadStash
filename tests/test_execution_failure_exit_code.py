"""An unrecovered transport failure (e.g. connection refused) must exit non-zero,
even though no response ever reached Capture/Expect to be judged. This is
separate from Expect assertion failures. See issue: HTTP connection refused
returns exit code 0 despite request failure.

Run:  python tests/test_execution_failure_exit_code.py
"""
import sys, json, threading, subprocess, tempfile, shutil, socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_results = []


def check(name, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), name)
    return bool(cond)


class _Handler(BaseHTTPRequestHandler):
    """GET /ok -> 200 {"ok": true}; GET /notfound -> 404 {"error": "not found"}."""

    def do_GET(self):
        if self.path == "/notfound":
            code, payload = 404, {"error": "not found"}
        else:
            code, payload = 200, {"ok": True}
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _closed_port() -> int:
    # Bind then immediately close to obtain a port number nothing is listening on.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_config(tmp: Path, name: str, yaml_text: str) -> subprocess.CompletedProcess:
    cfg = tmp / f"{name}.yml"
    cfg.write_text(yaml_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", "from payload_stash.main import main; main()",
         "run", str(cfg), "--out", str(tmp / "out" / name), "--yes"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True,
    )


CONNECTION_REFUSED_WITH_EXPECT = """
StashConfig:
  Name: ConnectionRefusedWithExpect
  Defaults:
    URLRoot: http://127.0.0.1:{closed_port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 2
  Sequences:
    - Name: Check
      Type: Sequential
      Requests:
        - Unreachable:
            Method: GET
            URLPath: /fixture.json
            Retry: null
            Capture:
              response: body
              status: status
            Expect:
              - status: 200
              - body: {{ type: object }}
"""

CONNECTION_REFUSED_NO_EXPECT = """
StashConfig:
  Name: ConnectionRefusedNoExpect
  Defaults:
    URLRoot: http://127.0.0.1:{closed_port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 2
  Sequences:
    - Name: Check
      Type: Sequential
      Requests:
        - Unreachable:
            Method: GET
            URLPath: /fixture.json
            Retry: null
"""

MIXED_SUCCESS_AND_FAILURE = """
StashConfig:
  Name: Mixed
  Defaults:
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 2
  Sequences:
    - Name: Check
      Type: Sequential
      Requests:
        - Good:
            Method: GET
            URLRoot: http://127.0.0.1:{good_port}
            URLPath: /ok
            Retry: null
            Expect:
              - status: 200
        - Bad:
            Method: GET
            URLRoot: http://127.0.0.1:{closed_port}
            URLPath: /fixture.json
            Retry: null
"""

SUCCESSFUL_AND_EXPECTED_404 = """
StashConfig:
  Name: SuccessAndExpected404
  Defaults:
    URLRoot: http://127.0.0.1:{good_port}
    FlowControl:
      DelaySeconds: 0
      TimeoutSeconds: 2
  Sequences:
    - Name: Check
      Type: Sequential
      Requests:
        - Good:
            Method: GET
            URLPath: /ok
            Retry: null
            Expect:
              - status: 200
        - NotFoundExpected:
            Method: GET
            URLPath: /notfound
            Retry: null
            Expect:
              - status: 404
"""


def run():
    closed_port = _closed_port()
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    good_port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = Path(tempfile.mkdtemp(prefix="ps-exec-failure-"))
    try:
        proc = _run_config(tmp, "refused-with-expect",
                            CONNECTION_REFUSED_WITH_EXPECT.format(closed_port=closed_port))
        check("connection refused with Expect -> exit non-zero", proc.returncode != 0)
        check("connection refused with Expect -> no assertions counted",
              "0 expect assertion(s) failed" not in proc.stdout)

        proc = _run_config(tmp, "refused-no-expect",
                            CONNECTION_REFUSED_NO_EXPECT.format(closed_port=closed_port))
        check("connection refused without Expect -> exit non-zero", proc.returncode != 0)

        proc = _run_config(tmp, "mixed",
                            MIXED_SUCCESS_AND_FAILURE.format(good_port=good_port, closed_port=closed_port))
        check("mixed success/failure run -> exit non-zero", proc.returncode != 0)

        proc = _run_config(tmp, "success-and-404",
                            SUCCESSFUL_AND_EXPECTED_404.format(good_port=good_port))
        check("successful run incl. expected 404 -> exit zero", proc.returncode == 0)

        total, passed = len(_results), sum(_results)
        print("\n%d/%d passed — %s" % (passed, total, "ALL GREEN" if passed == total else "RED"))
        sys.exit(0 if passed == total else 1)
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()

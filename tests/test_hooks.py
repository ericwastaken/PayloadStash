"""Script hooks: Hooks.BeforeAll, Hooks.AfterAll and per-sequence Before.

Plain-script style (matching tests/test_header_case.py). Each end-to-end case writes a config and
small /bin/sh hook scripts into a temp folder, runs PayloadStash against a local HTTP server, and
reads a trace file that both the hooks and the server append to.

Run:  python tests/test_hooks.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from payload_stash.config_schema import validate_config_data, build_resolved_config_dict  # noqa: E402
from payload_stash.hooks import build_argv, missing_captures  # noqa: E402

_results = []
_tmp_dirs = []


def check(name, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), name)
    return bool(cond)


# ---------------------------------------------------------------------------
# Local server: appends "REQ <METHOD> <path>" to the current trace file.
# ---------------------------------------------------------------------------

class _State:
    trace_path = None
    user_id = "U123"
    lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        with _State.lock:
            if _State.trace_path is not None:
                with open(_State.trace_path, "a", encoding="utf-8") as f:
                    f.write(f"REQ {self.command} {self.path}\n")
        if self.path.startswith("/login"):
            payload = {"userId": _State.user_id}
        else:
            payload = {"ok": True}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, *a):
        pass


HOOK_SCRIPTS = {
    # Appends its arguments to the trace and prints a line to stdout.
    "mark.sh": 'echo "HOOK $*" >> trace.txt\necho "marked $*"\n',
    # Appends to the trace, prints to stderr, and fails.
    "fail.sh": 'echo "HOOK fail $*" >> trace.txt\necho "failing on purpose" >&2\nexit 3\n',
    # Writes its argument count and each argument (one per line) to the file named by $1.
    "args.sh": 'out="$1"; shift\nprintf "%s\\n" "$#" > "$out"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$out"; done\n',
    # Prints its first argument to stdout and stderr, and saves it to got-secret.txt.
    "echo-secret.sh": 'echo "stdout: $1"\necho "stderr: $1" >&2\nprintf "%s" "$1" > got-secret.txt\n',
}

DEFAULTS = """
  Defaults:
    URLRoot: http://127.0.0.1:PORT
    FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 }
"""


def _run(config_text, port, extra_args=(), secrets_text=None, user_id="U123"):
    """Write the config and hook scripts into a temp folder and run PayloadStash on it."""
    tmp = Path(tempfile.mkdtemp(prefix="ps-hooks-"))
    _tmp_dirs.append(tmp)
    hooks_dir = tmp / "hooks"
    hooks_dir.mkdir()
    for name, body in HOOK_SCRIPTS.items():
        p = hooks_dir / name
        p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        p.chmod(0o755)
    cfg = tmp / "hooks-test.yml"
    cfg.write_text(config_text.replace("PORT", str(port)), encoding="utf-8")
    trace = tmp / "trace.txt"
    with _State.lock:
        _State.trace_path = trace
        _State.user_id = user_id
    cmd = [sys.executable, "-c", "from payload_stash.main import main; main()",
           "run", str(cfg), "--out", str(tmp / "out"), "--yes", *extra_args]
    if secrets_text is not None:
        sf = tmp / "secrets.env"
        sf.write_text(secrets_text, encoding="utf-8")
        cmd += ["--secrets", str(sf)]
    t0 = time.monotonic()
    # cwd is the repo, not the config folder: hooks must still resolve hooks/*.sh from the config's folder.
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=120)
    elapsed = time.monotonic() - t0
    with _State.lock:
        _State.trace_path = None

    def _read_all(pattern):
        return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (tmp / "out").rglob(pattern))

    return {
        "code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "console": proc.stdout + proc.stderr,
        "log": _read_all("*-run.log"),
        "report": _read_all("*-report.md"),
        "resolved": _read_all("*-resolved.yml"),
        "trace": trace.read_text(encoding="utf-8").splitlines() if trace.exists() else [],
        "tmp": tmp,
        "elapsed": elapsed,
    }


def _debug(res):
    print("---- exit", res["code"])
    print(res["console"][-2500:])
    print("---- log tail\n" + res["log"][-2500:])


# ---------------------------------------------------------------------------
# Unit tests: argument building (cases the end-to-end runs below don't cover)
# ---------------------------------------------------------------------------

def unit():
    check("captured number becomes its string form",
          build_argv("x ${captured:n}", {"n": 42}) == ["x", "42"])
    check("missing_captures lists each missing key once, in order",
          missing_captures(["${captured:b}", "${captured:a}${captured:b}", "${captured:c}"], {"c": 1}) == ["b", "a"])
    check("other placeholders expand as in $pattern (${uuidv4})",
          len(build_argv("x ${uuidv4}", {})[1]) == 36)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _cfg_with(hooks_yaml="", before_yaml=""):
    return f"""
StashConfig:
  Name: v
  Defaults: {{ URLRoot: http://x, FlowControl: {{ DelaySeconds: 0, TimeoutSeconds: 5 }} }}
{hooks_yaml}
  Sequences:
    - Name: s1
      Type: Sequential
{before_yaml}
      Requests: [ {{ a: {{ Method: GET, URLPath: /x }} }} ]
"""


def _rejected(text):
    try:
        validate_config_data(yaml.safe_load(text))
        return False
    except Exception:
        return True


def validation():
    check("valid Hooks + Before accepted", not _rejected(_cfg_with(
        '  Hooks:\n    BeforeAll: [a.sh, { Command: "b.sh x", TimeoutSeconds: 3 }]\n    AfterAll: ["c.sh ${captured:id}"]',
        '      Before: ["d.sh ${captured:id}"]')))
    check("unknown key under Hooks rejected", _rejected(_cfg_with("  Hooks: { Before: [a.sh] }")))
    check("unknown key in a hook mapping rejected", _rejected(_cfg_with("  Hooks: { BeforeAll: [{ Command: a, Shell: true }] }")))
    check("blank command rejected", _rejected(_cfg_with('  Hooks: { BeforeAll: ["   "] }')))
    check("unbalanced quote rejected", _rejected(_cfg_with("  Hooks: { AfterAll: [\"a 'b\"] }")))
    check("blank Before command rejected", _rejected(_cfg_with(before_yaml='      Before: [""]')))
    check("TimeoutSeconds 0 rejected", _rejected(_cfg_with("  Hooks: { BeforeAll: [{ Command: a, TimeoutSeconds: 0 }] }")))
    check("${captured:...} in BeforeAll rejected", _rejected(_cfg_with('  Hooks: { BeforeAll: ["a ${captured:x}"] }')))
    check("Before on a sequence is a known key (extra='forbid' still rejects typos)",
          _rejected(_cfg_with(before_yaml='      BeforeEach: [a.sh]')))

    # A secret in a hook argument needs the secrets file, as in $pattern templates.
    cfg = validate_config_data(yaml.safe_load(_cfg_with('  Hooks: { BeforeAll: ["a ${secrets:TOK}"] }')))
    try:
        build_resolved_config_dict(cfg)
        check("hook ${secrets:...} without a secrets file fails at resolve", False)
    except Exception:
        check("hook ${secrets:...} without a secrets file fails at resolve", True)

    # Resolved config keeps the hooks verbatim, in a stable place.
    cfg = validate_config_data(yaml.safe_load(_cfg_with(
        '  Hooks: { BeforeAll: [a.sh, { Command: "b.sh ${secrets:TOK}", TimeoutSeconds: 3 }] }',
        '      Before: ["d.sh ${captured:id}"]')))
    r = build_resolved_config_dict(cfg, secrets={"TOK": "real"}, redact_secrets=True)["StashConfig"]
    check("resolved: Hooks between Defaults and Sequences", list(r.keys()) == ["Name", "Defaults", "Hooks", "Sequences"])
    check("resolved: entries verbatim (placeholders unfilled)",
          r["Hooks"]["BeforeAll"] == ["a.sh", {"Command": "b.sh ${secrets:TOK}", "TimeoutSeconds": 3.0}])
    check("resolved: Before kept on its sequence", r["Sequences"][0]["Before"] == ["d.sh ${captured:id}"])

    # No hooks: no new keys in the resolved config.
    r = build_resolved_config_dict(validate_config_data(yaml.safe_load(_cfg_with())))["StashConfig"]
    check("no hooks: resolved config has no Hooks/Before keys",
          "Hooks" not in r and all("Before" not in s for s in r["Sequences"]))

    # validate CLI accepts a hook config.
    tmp = Path(tempfile.mkdtemp(prefix="ps-hooks-validate-"))
    _tmp_dirs.append(tmp)
    p = tmp / "v.yml"
    p.write_text(_cfg_with('  Hooks: { AfterAll: ["c.sh"] }'), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-c", "from payload_stash.main import main; main()", "validate", str(p)],
                          cwd=str(REPO), capture_output=True, text=True)
    check("validate CLI accepts a hook config", proc.returncode == 0 and "OK:" in proc.stdout)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def e2e(port):
    # 1) Order of execution, streaming output, log and report records.
    res = _run(f"""
StashConfig:
  Name: hooks-order
{DEFAULTS}
  Hooks:
    BeforeAll: ["hooks/mark.sh before-all-1", "hooks/mark.sh before-all-2"]
    AfterAll: ["hooks/mark.sh after-all ${{captured:userId}}"]
  Sequences:
    - Name: First
      Type: Sequential
      Requests:
        - Login: {{ Method: POST, URLPath: /login, Body: {{ create: true }}, Capture: {{ userId: body.userId }}, Expect: [ {{ status: 200 }} ] }}
    - Name: Second
      Type: Concurrent
      ConcurrencyLimit: 2
      Before: ["hooks/mark.sh before-second ${{captured:userId}}"]
      Requests:
        - A: {{ Method: GET, URLPath: /ok/a }}
        - B: {{ Method: GET, URLPath: /ok/b }}
""", port)
    t = res["trace"]
    ok = (res["code"] == 0
          and t[:4] == ["HOOK before-all-1", "HOOK before-all-2", "REQ POST /login", "HOOK before-second U123"]
          and sorted(t[4:6]) == ["REQ GET /ok/a", "REQ GET /ok/b"]
          and t[6:] == ["HOOK after-all U123"])
    if not check("order: BeforeAll, seq1, Before(seq2), seq2 (concurrent), AfterAll; exit 0", ok):
        print(t)
        _debug(res)
    check("hook stdout reaches the console", "marked before-all-1" in res["stdout"])
    check("run.log records the filled-in command and its output",
          "hooks/mark.sh before-second U123" in res["log"] and "marked before-second U123" in res["log"])
    check("report has a Hooks section", "## Hooks" in res["report"] and "hooks/mark.sh after-all U123" in res["report"])
    check("resolved config keeps the raw hook commands",
          "hooks/mark.sh before-second ${captured:userId}" in res["resolved"])

    # 2) Failing BeforeAll: later BeforeAll commands, all requests and AfterAll are skipped; exit 9.
    res = _run(f"""
StashConfig:
  Name: hooks-before-all-fails
{DEFAULTS}
  Hooks:
    BeforeAll: ["hooks/mark.sh one", "hooks/fail.sh two", "hooks/mark.sh three"]
    AfterAll: ["hooks/mark.sh after"]
  Sequences:
    - Name: S
      Type: Sequential
      Requests:
        - A: {{ Method: GET, URLPath: /ok/a }}
""", port)
    if not check("failing BeforeAll: no requests, no later hooks, no AfterAll; exit 9",
                 res["code"] == 9 and res["trace"] == ["HOOK one", "HOOK fail two"]):
        _debug(res)
    check("failing BeforeAll: console says which hook failed and that nothing was sent",
          "BeforeAll[2]" in res["stdout"] and "No requests were sent." in res["stdout"])
    check("hook stderr reaches console and run.log",
          "failing on purpose" in res["stdout"] and "failing on purpose" in res["log"])

    # 3) Failing Before on seq 2 of 3: seq 2 and 3 don't run, AfterAll does; exit 1.
    res = _run(f"""
StashConfig:
  Name: hooks-before-fails
{DEFAULTS}
  Hooks:
    AfterAll: ["hooks/mark.sh after"]
  Sequences:
    - {{ Name: S1, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/1 }} }} ] }}
    - {{ Name: S2, Type: Sequential, Before: ["hooks/fail.sh s2"], Requests: [ {{ B: {{ Method: GET, URLPath: /ok/2 }} }} ] }}
    - {{ Name: S3, Type: Sequential, Requests: [ {{ C: {{ Method: GET, URLPath: /ok/3 }} }} ] }}
""", port)
    if not check("failing Before: later sequences skipped, AfterAll runs; exit 1",
                 res["code"] == 1 and res["trace"] == ["REQ GET /ok/1", "HOOK fail s2", "HOOK after"]):
        _debug(res)

    # 4a) Failing AfterAll with passing Expect: exit 1.
    after_fails = f"""
StashConfig:
  Name: hooks-after-all-fails
{DEFAULTS}
  Hooks:
    AfterAll: ["hooks/fail.sh after"]
  Sequences:
    - {{ Name: S, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a, Expect: [ {{ status: EXPECTED }} ] }} }} ] }}
"""
    res = _run(after_fails.replace("EXPECTED", "200"), port)
    if not check("failing AfterAll (Expect passed): exit 1",
                 res["code"] == 1 and res["trace"] == ["REQ GET /ok/a", "HOOK fail after"]
                 and "AfterAll[1] failed" in res["stdout"]
                 and "expect assertion(s) failed" not in res["stdout"]):
        _debug(res)
    # 4b) Failing Expect: AfterAll still runs; when it fails too, exit 1 and both are reported.
    res = _run(after_fails.replace("EXPECTED", "201"), port)
    check("failing Expect: AfterAll still runs; both failures reported; exit 1",
          res["code"] == 1 and res["trace"] == ["REQ GET /ok/a", "HOOK fail after"]
          and "expect assertion(s) failed" in res["stdout"] and "AfterAll[1] failed" in res["stdout"])

    # 5) Captured value with spaces, quotes and shell syntax arrives as one argument, never run.
    tricky = "a b 'c\" $(touch pwned) ; touch pwned2 `touch pwned3`"
    res = _run(f"""
StashConfig:
  Name: hooks-one-arg
{DEFAULTS}
  Sequences:
    - Name: First
      Type: Sequential
      Requests:
        - Login: {{ Method: POST, URLPath: /login, Capture: {{ userId: body.userId }} }}
    - Name: Second
      Type: Sequential
      Before: ["hooks/args.sh args.txt ${{captured:userId}}"]
      Requests:
        - A: {{ Method: GET, URLPath: /ok/a }}
""", port, user_id=tricky)
    args_file = res["tmp"] / "args.txt"
    got = args_file.read_text(encoding="utf-8").splitlines() if args_file.exists() else None
    if not check("captured value is exactly one argument", res["code"] == 0 and got == ["1", tricky]):
        print(got)
        _debug(res)
    check("captured value never ran as shell code",
          not any((res["tmp"] / n).exists() for n in ("pwned", "pwned2", "pwned3")))

    # 6) Missing captures: a key never captured (nope) and a key captured as null (userId, path
    # missing in the response). The hook doesn't run, later sequences don't run; exit 1.
    res = _run(f"""
StashConfig:
  Name: hooks-missing-capture
{DEFAULTS}
  Hooks:
    AfterAll: ["hooks/mark.sh after"]
  Sequences:
    - {{ Name: S1, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/1, Capture: {{ userId: body.missing }} }} }} ] }}
    - {{ Name: S2, Type: Sequential, Before: ["hooks/mark.sh s2 ${{captured:userId}} ${{captured:nope}}"], Requests: [ {{ B: {{ Method: GET, URLPath: /ok/2 }} }} ] }}
    - {{ Name: S3, Type: Sequential, Requests: [ {{ C: {{ Method: GET, URLPath: /ok/3 }} }} ] }}
""", port)
    if not check("missing and null captures: hook not run, later sequences skipped; exit 1",
                 res["code"] == 1 and res["trace"] == ["REQ GET /ok/1", "HOOK after"]
                 and "captured value(s) not available: userId, nope" in res["stdout"]):
        _debug(res)

    # 7) Redaction: secrets never reach console, log or report; the hook still gets the real value.
    secret = "s3cr3t-value"
    res = _run(f"""
StashConfig:
  Name: hooks-redaction
{DEFAULTS}
  Hooks:
    BeforeAll: ["hooks/echo-secret.sh ${{secrets:TOKEN}}"]
  Sequences:
    - {{ Name: S, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a }} }} ] }}
""", port, secrets_text=f"TOKEN={secret}\n")
    got_secret = res["tmp"] / "got-secret.txt"
    check("secret argument reaches the hook unredacted",
          res["code"] == 0 and got_secret.exists() and got_secret.read_text(encoding="utf-8") == secret)
    leaked = [name for name in ("console", "log", "report", "resolved") if secret in res[name]]
    if not check("secret redacted in console, run.log, report and resolved config", not leaked):
        print("leaked into:", leaked)
    check("redacted output and command still logged",
          "stdout: ***REDACTED***" in res["log"] and "stderr: ***REDACTED***" in res["log"]
          and "hooks/echo-secret.sh ***REDACTED***" in res["log"])

    # 8) Dry run: no hook runs; the log says what would run.
    res = _run(f"""
StashConfig:
  Name: hooks-dry-run
{DEFAULTS}
  Hooks:
    BeforeAll: ["hooks/mark.sh before"]
    AfterAll: ["hooks/mark.sh after"]
  Sequences:
    - {{ Name: S, Type: Sequential, Before: ["hooks/mark.sh seq"], Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a }} }} ] }}
""", port, extra_args=["--dry-run"])
    check("dry run: no hook runs; exit 0", res["code"] == 0 and res["trace"] == [])
    check("dry run: log lists the hooks that would run",
          all(f"hooks/mark.sh {name}" in res["log"] for name in ("before", "seq", "after"))
          and res["log"].count("DRY-RUN") == 4)  # 3 hooks + 1 request

    # 9) Timeout: a hung command is killed; the run stops.
    res = _run(f"""
StashConfig:
  Name: hooks-timeout
{DEFAULTS}
  Hooks:
    BeforeAll: [{{ Command: "sleep 30", TimeoutSeconds: 1 }}]
  Sequences:
    - {{ Name: S, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a }} }} ] }}
""", port)
    if not check("timeout: killed after TimeoutSeconds; exit 9; no requests",
                 res["code"] == 9 and res["trace"] == [] and res["elapsed"] < 15
                 and "timed out" in res["stdout"]):
        _debug(res)

    # 9b) A command that can't start fails the hook.
    res = _run(f"""
StashConfig:
  Name: hooks-not-found
{DEFAULTS}
  Hooks:
    BeforeAll: ["hooks/does-not-exist.sh"]
  Sequences:
    - {{ Name: S, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a }} }} ] }}
""", port)
    check("command not found: hook fails; exit 9", res["code"] == 9 and "could not start" in res["stdout"])

    # 11) No hooks: no hook output anywhere.
    res = _run(f"""
StashConfig:
  Name: hooks-none
{DEFAULTS}
  Sequences:
    - {{ Name: S, Type: Sequential, Requests: [ {{ A: {{ Method: GET, URLPath: /ok/a }} }} ] }}
""", port)
    check("no hooks: no hook lines in console, run.log or report; exit 0",
          res["code"] == 0 and "Hook" not in res["stdout"] and "Hook" not in res["log"]
          and "## Hooks" not in res["report"])


def run():
    unit()
    validation()
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        e2e(srv.server_address[1])
    finally:
        srv.shutdown()
        srv.server_close()
        for d in _tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
    passed = sum(_results)
    total = len(_results)
    print()
    print(f"{passed}/{total} passed" + (" — ALL GREEN" if passed == total else " — FAILURES"))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    if os.name != "posix":
        print("SKIP: hook tests use /bin/sh scripts (POSIX only)")
        sys.exit(0)
    run()

"""URLRoot / URLPath operator support ($secrets, $dynamic, $pattern, inline secrets, ${captured}).

Plain-script style (matching tests/test_asserts.py). Run:
    .venv/bin/python tests/test_url_operators.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payload_stash.config_schema import validate_config_data, build_resolved_config_dict
from payload_stash.config_utility import resolve_deferred

_results = []


def check(name, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), name)
    return cond


def _req(y, secrets=None, redact=False, seq=0, i=0):
    cfg = validate_config_data(yaml.safe_load(y))
    r = build_resolved_config_dict(cfg, secrets=secrets, redact_secrets=redact)
    item = r["StashConfig"]["Sequences"][seq]["Requests"][i]
    return next(iter(item.values()))


def _rejected(y):
    try:
        validate_config_data(yaml.safe_load(y))
        return False
    except Exception:
        return True


def _dry_run(y, secrets_text=None, null_request_root=False):
    tmp = Path(tempfile.mkdtemp(prefix="ps-url-operators-"))
    try:
        config = tmp / "config.yml"
        config.write_text(y, encoding="utf-8")
        program = "from payload_stash.main import main; main()"
        if null_request_root:
            program = """
import payload_stash.main as app

original_build = app.build_resolved_config_dict

def build_with_null_request_root(*args, **kwargs):
    resolved = original_build(*args, **kwargs)
    request = next(iter(resolved["StashConfig"]["Sequences"][0]["Requests"][0].values()))
    request["URLRoot"] = None
    return resolved

app.build_resolved_config_dict = build_with_null_request_root
app.main()
"""
        command = [
            sys.executable, "-c", program,
            "run", str(config), "--out", str(tmp / "out"), "--dry-run", "--yes",
        ]
        if secrets_text is not None:
            secrets = tmp / "secrets.env"
            secrets.write_text(secrets_text, encoding="utf-8")
            command.extend(["--secrets", str(secrets)])
        proc = subprocess.run(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
        )
        logs = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (tmp / "out").rglob("*.log")
        )
        return proc, logs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run():
    # URLRoot via $dynamic (resolve-time)
    y = """
dynamics:
  patterns: { host: { template: "https://api-${choice:e}.example.com" } }
  sets: { e: ["stage"] }
StashConfig:
  Name: t
  Defaults: { URLRoot: { $dynamic: host }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
"""
    check("URLRoot $dynamic resolves", _req(y)["URLRoot"] == "https://api-stage.example.com")

    # URLRoot via $secrets mapping (actual + redacted)
    y = """
StashConfig:
  Name: t
  Defaults: { URLRoot: { $secrets: H }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
"""
    check("URLRoot $secrets mapping (actual)", _req(y, secrets={"H": "https://real"})["URLRoot"] == "https://real")
    check("URLRoot $secrets mapping (redacted)", _req(y, secrets={"H": "https://real"}, redact=True)["URLRoot"] == "***REDACTED***")

    # URLPath inline secret (actual + redacted)
    y = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://x, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: "/seg/{ $secrets: S }" } } ]}
"""
    check("URLPath inline secret (actual)", _req(y, secrets={"S": "v1"})["URLPath"] == "/seg/v1")
    check("URLPath inline secret (redacted)", _req(y, secrets={"S": "v1"}, redact=True)["URLPath"] == "/seg/***REDACTED***")

    # URLPath $pattern with ${captured} defers, then resolves at request time
    y = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://x, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: { $pattern: "/things/${captured:id}" } } } ]}
"""
    up = _req(y)["URLPath"]
    check("URLPath $pattern deferred at build", isinstance(up, dict) and "$deferred" in up)
    check("URLPath $pattern resolves w/ capture at request time",
          resolve_deferred(up, captures={"id": "XYZ"}) == "/things/XYZ")

    # validator: URLRoot as operator mapping accepted (HTTP present); missing URLRoot rejected
    ok_map = """
StashConfig:
  Name: t
  Defaults: { URLRoot: { $secrets: H }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
"""
    try:
        validate_config_data(yaml.safe_load(ok_map)); check("URLRoot operator mapping accepted", True)
    except Exception:
        check("URLRoot operator mapping accepted", False)

    missing = """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
"""
    try:
        validate_config_data(yaml.safe_load(missing)); check("missing URLRoot w/ HTTP rejected", False)
    except Exception as exc:
        message = str(exc)
        check("missing URLRoot w/ HTTP rejected", True)
        check(
            "missing URLRoot lists every supported operator",
            all(operator in message for operator in ("$secrets", "$dynamic", "$pattern", "$timestamp", "$func")),
        )

    # request-level URLRoot overrides Defaults.URLRoot
    y = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - Name: s
      Type: Sequential
      Requests:
        - { a: { Method: GET, URLPath: /x, URLRoot: https://override.example.com } }
        - { b: { Method: GET, URLPath: /y } }
"""
    check("request URLRoot overrides Defaults", _req(y, i=0)["URLRoot"] == "https://override.example.com")
    check("request w/o URLRoot inherits Defaults", _req(y, i=1)["URLRoot"] == "https://default.example.com")

    # request-level URLRoot supports operators ($secrets)
    y = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: { $secrets: H } } } ]}
"""
    check("request URLRoot $secrets (actual)", _req(y, secrets={"H": "https://real"})["URLRoot"] == "https://real")
    check("request URLRoot $secrets (redacted)", _req(y, secrets={"H": "https://real"}, redact=True)["URLRoot"] == "***REDACTED***")

    # Remaining URLRoot operators work at both effective-root scopes.
    y = """
dynamics:
  patterns: { host: { template: "https://api-${choice:e}.example.com" } }
  sets: { e: ["stage"] }
StashConfig:
  Name: t
  Defaults: { URLRoot: { $pattern: "https://pattern.example.com" }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - Name: s
      Type: Sequential
      Requests:
        - { a: { Method: GET, URLPath: /x } }
        - { b: { Method: GET, URLPath: /y, URLRoot: { $dynamic: host } } }
"""
    pattern_root = _req(y, i=0)["URLRoot"]
    check(
        "Defaults URLRoot $pattern resolves at request time",
        resolve_deferred(pattern_root) == "https://pattern.example.com",
    )
    check("request URLRoot $dynamic resolves", _req(y, i=1)["URLRoot"] == "https://api-stage.example.com")

    # Defaults.URLRoot may be omitted when every HTTP request has its own URLRoot
    all_own = """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: https://own.example.com } } ]}
"""
    try:
        validate_config_data(yaml.safe_load(all_own)); check("Defaults.URLRoot omitted OK when all requests have URLRoot", True)
    except Exception:
        check("Defaults.URLRoot omitted OK when all requests have URLRoot", False)
    check("all-own URLRoot resolves", _req(all_own)["URLRoot"] == "https://own.example.com")

    # ...but still rejected when any HTTP request lacks its own URLRoot
    mixed_missing = """
StashConfig:
  Name: t
  Defaults: { FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - Name: s
      Type: Sequential
      Requests:
        - { a: { Method: GET, URLPath: /x, URLRoot: https://own.example.com } }
        - { b: { Method: GET, URLPath: /y } }
"""
    try:
        validate_config_data(yaml.safe_load(mixed_missing)); check("missing URLRoot for uncovered request rejected", False)
    except Exception:
        check("missing URLRoot for uncovered request rejected", True)

    # Invalid request overrides must not bypass Defaults.URLRoot coverage or
    # override a valid default with an unusable value.
    invalid_request_roots = [
        '""',
        '"   "',
        '{}',
        '{ foo: bar }',
        '{ $unknown: value }',
        '{ $secrets: " " }',
        '{ $dynamic: 1 }',
        '{ $pattern: [] }',
        '{ $func: uuidv4 }',
        '{ $timestamp: 123 }',
        '{ $func: timestamp, extra: true }',
        '{ $timestamp: { format: epoch_s, extra: true } }',
        '{ $timestamp: epoch_s, when: later }',
        '{ $secrets: H, $timestamp: epoch_s }',
    ]
    for invalid_root in invalid_request_roots:
        y = f"""
StashConfig:
  Name: t
  Defaults: {{ URLRoot: https://default.example.com, FlowControl: {{ DelaySeconds: 0, TimeoutSeconds: 5 }} }}
  Sequences:
    - {{Name: s, Type: Sequential, Requests: [ {{ a: {{ Method: GET, URLPath: /x, URLRoot: {invalid_root} }} }} ]}}
"""
        check(f"invalid request URLRoot rejected: {invalid_root}", _rejected(y))

        y = f"""
StashConfig:
  Name: t
  Defaults: {{ URLRoot: {invalid_root}, FlowControl: {{ DelaySeconds: 0, TimeoutSeconds: 5 }} }}
  Sequences:
    - {{Name: s, Type: Sequential, Requests: [ {{ a: {{ Method: GET, URLPath: /x }} }} ]}}
"""
        check(f"invalid Defaults.URLRoot rejected: {invalid_root}", _rejected(y))

    # Both timestamp operator forms produce integer roots at either scope and
    # pass request processing through string conversion.
    timestamp_roots = {
        "Defaults $func": """
StashConfig:
  Name: t
  Defaults: { URLRoot: { $func: timestamp, format: epoch_s, when: request }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
""",
        "Defaults $timestamp": """
StashConfig:
  Name: t
  Defaults: { URLRoot: { $timestamp: { format: epoch_s, when: request } }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
""",
        "request $func": """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: { $func: timestamp, format: epoch_s, when: request } } } ]}
""",
        "request $timestamp": """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: { $timestamp: { format: epoch_s, when: request } } } } ]}
""",
    }
    for scope_and_operator, timestamp_root in timestamp_roots.items():
        check(f"supported {scope_and_operator} URLRoot accepted", not _rejected(timestamp_root))
        proc, logs = _dry_run(timestamp_root)
        check(f"integer {scope_and_operator} URLRoot passes request processing", proc.returncode == 0)
        check(
            f"integer {scope_and_operator} URLRoot is stringified in assembled URL",
            re.search(r"URL: \d+/x", logs) is not None,
        )

    # Operator results that resolve to a blank string remain unusable at request time.
    blank_secret_root = """
StashConfig:
  Name: t
  Defaults: { URLRoot: { $secrets: H }, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x } } ]}
"""
    proc, logs = _dry_run(blank_secret_root, 'H="   "\n')
    check(
        "blank resolved URLRoot rejected before dispatch",
        "Operation Cancelled" in proc.stdout and "URL:" not in logs,
    )

    blank_request_secret_root = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: { $secrets: H } } } ]}
"""
    proc, logs = _dry_run(blank_request_secret_root, 'H="   "\n')
    check(
        "blank resolved request URLRoot rejected without default fallback",
        "Operation Cancelled" in proc.stdout and "URL:" not in logs,
    )

    # A present request-level URLRoot that resolves to null must not inherit Defaults.URLRoot.
    explicit_null_root = """
StashConfig:
  Name: t
  Defaults: { URLRoot: https://default.example.com, FlowControl: { DelaySeconds: 0, TimeoutSeconds: 5 } }
  Sequences:
    - {Name: s, Type: Sequential, Requests: [ { a: { Method: GET, URLPath: /x, URLRoot: https://override.example.com } } ]}
"""
    proc, logs = _dry_run(explicit_null_root, null_request_root=True)
    check(
        "explicit null request URLRoot rejected without default fallback",
        "Operation Cancelled" in proc.stdout and "URL:" not in logs,
    )

    total, passed = len(_results), sum(_results)
    print("\n%d/%d passed — %s" % (passed, total, "ALL GREEN" if passed == total else "RED"))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    run()

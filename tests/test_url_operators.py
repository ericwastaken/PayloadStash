"""URLRoot / URLPath operator support ($secrets, $dynamic, $pattern, inline secrets, ${captured}).

Plain-script style (matching tests/test_asserts.py). Run:
    .venv/bin/python tests/test_url_operators.py
"""
import sys
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
    except Exception:
        check("missing URLRoot w/ HTTP rejected", True)

    total, passed = len(_results), sum(_results)
    print("\n%d/%d passed — %s" % (passed, total, "ALL GREEN" if passed == total else "RED"))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    run()

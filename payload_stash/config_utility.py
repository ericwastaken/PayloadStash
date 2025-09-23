from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import uuid
import random
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple


def timestamp(fmt: Literal["epoch_ms", "epoch_s", "iso_8601"] = "iso_8601"):
    """
    Return the current UTC timestamp in the requested format.

    - epoch_ms: milliseconds since Unix epoch (int)
    - epoch_s: seconds since Unix epoch (int)
    - iso_8601: ISO 8601 string in UTC with 'Z' suffix, e.g., 2025-09-17T19:35:00Z
    """
    now = datetime.now(timezone.utc)
    if fmt == "epoch_ms":
        return int(now.timestamp() * 1000)
    if fmt == "epoch_s":
        return int(now.timestamp())
    if fmt == "iso_8601":
        # Use Z suffix to indicate UTC
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(f"Unsupported timestamp format: {fmt}")


_HEX_CHARS = "0123456789ABCDEF"
_PLACEHOLDER_RE = re.compile(r"\$\{([^}:]+)(?::([^}:]+))?(?::([^}]+))?\}")


def dynamic_expand(template: str, sets: Optional[Dict[str, List[str]]] = None, *, secrets: Optional[Dict[str, str]] = None, redact_secrets: bool = False) -> str:
    """
    Expand a dynamic template string using supported placeholders.

    Supported placeholders:
      - ${hex:N}                  → N random hex characters (uppercase A–F)
      - ${alphanumeric:N}         → N random characters 0-9 A-Z a-z
      - ${numeric:N}              → N random digits 0-9
      - ${alpha:N}                → N random letters A-Z a-z
      - ${uuidv4}                 → a UUID v4 string
      - ${choice:setName}         → pick 1 element from sets[setName]
      - ${timestamp[:format]}     → current UTC timestamp; format one of epoch_ms | epoch_s | iso_8601 (default iso_8601)
      - ${@timestamp[:format]}    → alias for ${timestamp[:format]}
      - ${secrets:KEY}            → inject secret by KEY from the --secrets file (redacted when requested)
        Also supported in inline form within strings: "... { $secrets: KEY } ..."
    """
    sets = sets or {}

    def repl(m: re.Match) -> str:
        name = m.group(1)
        arg1 = m.group(2)
        arg2 = m.group(3)
        if name == "hex":
            if not arg1 or not arg1.isdigit():
                raise ValueError(f"${{hex:N}} requires integer N; got: {arg1!r}")
            n = int(arg1)
            return "".join(random.choice(_HEX_CHARS) for _ in range(n))
        if name == "uuidv4":
            return str(uuid.uuid4())
        if name == "timestamp" or name == "@timestamp":
            fmt = arg1 or "iso_8601"
            return str(timestamp(fmt))
        if name == "secrets" or name == "secret":
            key = arg1
            if not key:
                raise ValueError("${secrets:KEY} requires a secret key name")
            if secrets is None:
                raise ValueError(f"Secret '{key}' requested but no --secrets file was provided")
            if key not in secrets:
                raise ValueError(f"Unknown secret requested: '{key}'")
            return "***REDACTED***" if redact_secrets else str(secrets[key])
        if name == "choice":
            if not arg1:
                raise ValueError("${choice:setName} requires a set name")
            if arg2 is not None:
                # Disallow multi-selection/repeat for choice to enforce single selection
                raise ValueError("${choice:setName} does not support multiple selections")
            pool = sets.get(arg1)
            if pool is None:
                raise ValueError(f"Unknown choice set: {arg1}")
            return random.choice(pool)
        if name == "alphanumeric":
            if not arg1 or not arg1.isdigit():
                raise ValueError(f"${{alphanumeric:N}} requires integer N; got: {arg1!r}")
            n = int(arg1)
            chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            return "".join(random.choice(chars) for _ in range(n))
        if name == "numeric":
            if not arg1 or not arg1.isdigit():
                raise ValueError(f"${{numeric:N}} requires integer N; got: {arg1!r}")
            n = int(arg1)
            chars = "0123456789"
            return "".join(random.choice(chars) for _ in range(n))
        if name == "alpha":
            if not arg1 or not arg1.isdigit():
                raise ValueError(f"${{alpha:N}} requires integer N; got: {arg1!r}")
            n = int(arg1)
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            return "".join(random.choice(chars) for _ in range(n))
        # Unknown placeholder: leave as-is to avoid data loss
        return m.group(0)

    # First, handle ${...} placeholders including ${secrets:KEY}
    out = _PLACEHOLDER_RE.sub(repl, template)

    # Then, support inline secret syntax inside templates: "{ $secrets: KEY }"
    try:
        _inline = re.compile(r"\{\s*\$secrets\s*:\s*([A-Za-z0-9_\-\.]+)\s*\}")
        def _inline_rep(m: re.Match) -> str:
            k = m.group(1)
            if secrets is None:
                raise ValueError(f"Secret '{k}' requested but no --secrets file was provided")
            if k not in secrets:
                raise ValueError(f"Unknown secret requested: '{k}'")
            return "***REDACTED***" if redact_secrets else str(secrets[k])
        out = _inline.sub(_inline_rep, out)
    except Exception:
        # Leave as-is if replacement fails unexpectedly
        pass

    return out


def resolve_deferred(value: Any, *, secrets: Optional[Dict[str, str]] = None, redact_secrets: bool = False) -> Any:
    """Recursively resolve any "$deferred" function or dynamic objects.

    Supported deferred marker shapes:
      {"$deferred": {"func": "timestamp", "format": "iso_8601"}}
      {"$deferred": {"dynamic": {"template": "...", "sets": {...}}}}
    """
    if isinstance(value, Mapping):
        if "$deferred" in value:
            payload = value["$deferred"]
            if not isinstance(payload, Mapping):
                return value
            func = payload.get("func")
            if func == "timestamp":
                fmt = payload.get("format") or payload.get("fmt") or "iso_8601"
                return timestamp(fmt)
            dyn = payload.get("dynamic")
            if isinstance(dyn, Mapping):
                template = dyn.get("template")
                sets = dyn.get("sets") or {}
                if not isinstance(template, str):
                    return value
                return dynamic_expand(template, sets, secrets=secrets, redact_secrets=redact_secrets)
            # Unknown deferred payload: return as-is
            return value
        # else recurse into mapping
        return {k: resolve_deferred(v, secrets=secrets, redact_secrets=redact_secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_deferred(v, secrets=secrets, redact_secrets=redact_secrets) for v in value]
    return value


def load_secrets_file(path: str | Path) -> Dict[str, str]:
    """Load a .env-like secrets file with KEY=VALUE lines.

    Rules:
    - Preserve case of keys and values (case-sensitive).
    - Lines beginning with '#' or blank lines are ignored.
    - Allows values to contain any characters; leading/trailing whitespace around key and separator is trimmed, but not inside value.
    - Supports quoted values; surrounding single or double quotes are removed if present.
    - Duplicate keys: last one wins.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Secrets file not found: {p}")
    secrets: Dict[str, str] = {}
    with p.open('r', encoding='utf-8') as f:
        for idx, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            # Allow inline comments if preceded by at least one space before '#'
            # but do not strip if '#' appears inside quotes
            # Simple approach: split on first '='
            if '=' not in line:
                raise ValueError(f"Invalid secrets line {idx}: expected KEY=VALUE")
            key, val = line.split('=', 1)
            key = key.strip()
            # Preserve value as-is except trim surrounding spaces
            val = val.strip()
            # Strip surrounding quotes if present
            if (len(val) >= 2) and ((val[0] == val[-1]) and val[0] in ('"', "'")):
                val = val[1:-1]
            if not key:
                raise ValueError(f"Invalid secrets line {idx}: empty key")
            secrets[key] = val
    return secrets

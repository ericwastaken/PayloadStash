from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
import random
from typing import Any, Dict, List, Literal, Mapping, Optional


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


def dynamic_expand(template: str, sets: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Expand a dynamic template string using supported placeholders.

    Supported placeholders:
      - ${hex:N}             → N random hex characters (uppercase A–F)
      - ${uuidv4}            → a UUID v4 string
      - ${choice:setName}    → pick 1 element from sets[setName]
      - ${choice:setName:K}  → pick K elements independently and concatenate
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
        if name == "choice":
            if not arg1:
                raise ValueError("${choice:setName[:K] } requires a set name")
            pool = sets.get(arg1)
            if pool is None:
                raise ValueError(f"Unknown choice set: {arg1}")
            k = 1
            if arg2:
                if not arg2.isdigit():
                    raise ValueError(f"Repeat K for choice must be integer; got: {arg2!r}")
                k = int(arg2)
            return "".join(random.choice(pool) for _ in range(k))
        # Unknown placeholder: leave as-is to avoid data loss
        return m.group(0)

    return _PLACEHOLDER_RE.sub(repl, template)


def resolve_deferred(value: Any) -> Any:
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
                return dynamic_expand(template, sets)
            # Unknown deferred payload: return as-is
            return value
        # else recurse into mapping
        return {k: resolve_deferred(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_deferred(v) for v in value]
    return value

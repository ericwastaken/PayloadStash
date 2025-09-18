from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal


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


def resolve_deferred(value: Any) -> Any:
    """Recursively resolve any "$deferred" function objects.

    Supported deferred marker shape:
      {"$deferred": {"func": "timestamp", "format": "iso_8601"}}
    """
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        if "$deferred" in value:
            payload = value["$deferred"]
            if not isinstance(payload, Mapping):
                return value
            func = payload.get("func")
            if func == "timestamp":
                fmt = payload.get("format") or payload.get("fmt") or "iso_8601"
                return timestamp(fmt)
            # Unknown deferred func: return as-is
            return value
        # else recurse into mapping
        return {k: resolve_deferred(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_deferred(v) for v in value]
    return value

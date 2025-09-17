from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator, field_validator


# Enums for constrained values
class Method(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class SequenceType(str, Enum):
    Sequential = "Sequential"
    Concurrent = "Concurrent"


class BackoffStrategy(str, Enum):
    fixed = "fixed"
    exponential = "exponential"


class Retry(BaseModel):
    # Ensure enums are serialized as their values when dumping to dicts
    model_config = ConfigDict(extra='forbid', use_enum_values=True)

    Attempts: int = Field(..., ge=1)
    BackoffStrategy: BackoffStrategy
    BackoffSeconds: float = Field(..., ge=0)
    Multiplier: Optional[float] = Field(None, gt=0)
    MaxBackoffSeconds: Optional[float] = Field(None, ge=0)
    MaxElapsedSeconds: Optional[float] = Field(None, ge=0)
    # README varies wording for Jitter; allow bool or literal strings
    Jitter: Optional[Union[bool, str]] = None
    RetryOnStatus: Optional[List[int]] = None
    RetryOnNetworkErrors: Optional[bool] = None
    RetryOnTimeouts: Optional[bool] = None


class SectionMaps(BaseModel):
    model_config = ConfigDict(extra='forbid')

    URLRoot: Optional[str] = None
    Headers: Optional[Dict[str, Any]] = None
    Body: Optional[Dict[str, Any]] = None
    Query: Optional[Dict[str, Any]] = None
    # Optional global retry
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Method: Method
    URLPath: str
    Headers: Optional[Dict[str, Any]] = None
    Body: Optional[Dict[str, Any]] = None
    Query: Optional[Dict[str, Any]] = None
    TimeoutSeconds: Optional[int] = Field(None, ge=0)
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')


class RequestItem(BaseModel):
    """Represents one mapping item in Requests list: { <Key>: <Request> }"""

    key: str
    value: Request

    @classmethod
    def from_mapping(cls, m: Dict[str, Any]) -> "RequestItem":
        if not isinstance(m, dict) or len(m) != 1:
            raise ValueError("Each Requests entry must be a single-key mapping: { <Key>: {Request...} }")
        k, v = next(iter(m.items()))
        req = Request(**v)
        return cls(key=k, value=req)


class Sequence(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Name: str
    Type: SequenceType
    ConcurrencyLimit: Optional[int] = Field(None, ge=1)
    Requests: List[RequestItem]

    @field_validator('Requests', mode='before')
    @classmethod
    def validate_requests(cls, v: Any) -> List[RequestItem]:
        if not isinstance(v, list) or not v:
            raise ValueError("Requests must be a non-empty list of single-key mappings")
        items: List[RequestItem] = []
        for i, elem in enumerate(v):
            try:
                items.append(RequestItem.from_mapping(elem))
            except Exception as e:
                raise ValueError(f"Requests[{i}]: {e}")
        return items

    @model_validator(mode='after')
    def check_concurrency(self) -> 'Sequence':
        t: SequenceType = self.Type
        limit: Optional[int] = self.ConcurrencyLimit
        if t == SequenceType.Concurrent and limit is None:
            # Make it required for Concurrent to encourage explicitness
            raise ValueError("ConcurrencyLimit is required when Type is 'Concurrent'")
        if t == SequenceType.Sequential and limit is not None:
            # For sequential, ConcurrencyLimit should not be set
            raise ValueError("ConcurrencyLimit should not be set when Type is 'Sequential'")
        return self


class StashConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Name: str
    Defaults: Optional[SectionMaps] = None
    Forced: Optional[SectionMaps] = None
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')
    Sequences: List[Sequence]


class TopLevelConfig(BaseModel):
    """Top-level model. Allows extra keys (anchors/aliases) but requires StashConfig."""

    model_config = ConfigDict(extra='allow')

    StashConfig: StashConfig


def validate_config_data(data: Dict[str, Any]) -> TopLevelConfig:
    """Validate already-loaded YAML data against the schema.

    Returns the parsed TopLevelConfig or raises ValidationError.
    Additionally, provides a friendlier message if the top-level `StashConfig`
    section is missing but common StashConfig children are present at the root.
    """
    if isinstance(data, dict) and 'StashConfig' not in data:
        likely_children = {'Defaults', 'Forced', 'Retry', 'Sequences', 'Name'}
        present = likely_children.intersection(data.keys())
        if present:
            raise ValueError(
                "Top-level 'StashConfig' section is missing. Your YAML appears to place "
                f"{sorted(present)} at the root. Wrap your config like:\n\n"
                "StashConfig:\n"
                "  Name: <YourName>\n"
                "  Defaults: { ... }  # optional\n"
                "  Forced:   { ... }  # optional\n"
                "  Retry:    { ... }  # optional\n"
                "  Sequences: [ ... ]\n"
            )
    return TopLevelConfig(**data)


def validate_config_path(path: Union[str, Path]) -> TopLevelConfig:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return validate_config_data(data)


def format_validation_error(err: Union[ValidationError, Exception]) -> str:
    """Return a human-friendly string for Pydantic validation errors."""
    if isinstance(err, ValidationError):
        lines: List[str] = ["Validation failed with the following errors:"]
        for e in err.errors():
            loc = ".".join(str(x) for x in e.get('loc', []))
            msg = e.get('msg', 'Invalid value')
            typ = e.get('type', '')
            lines.append(f" - {loc}: {msg} ({typ})")
        return "\n".join(lines)
    else:
        return f"Validation failed: {err}"


# ---------------------------
# Resolution helpers
# ---------------------------

def _copy_map(m: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if m is None:
        return None
    # shallow copy is fine because values are primitives or nested dicts already materialized by yaml loader
    return dict(m)


def build_resolved_config_dict(cfg: TopLevelConfig) -> Dict[str, Any]:
    """Build a fully-resolved config dict with Defaults and Forced applied into each Request.

    Rules:
    - For sections Headers/Body/Query: use request section if present, else Defaults.section; then overlay Forced.section.
    - Retry precedence respects explicit nulls: request.Retry (even null) > Defaults.Retry (even null) > StashConfig.Retry (even null).
      Only fall through when a level omits the Retry field entirely.
    - Anchors are already resolved by yaml.safe_load; we also ensure the resulting dict contains plain maps.
    """
    sc = cfg.StashConfig
    defaults = sc.Defaults
    forced = sc.Forced

    # Helper to detect if a Pydantic field was provided (even if its value is None)
    def _provided(m: Any, field_name: str) -> bool:
        try:
            fs = getattr(m, 'model_fields_set')
        except Exception:
            fs = None
        if isinstance(fs, set):
            return field_name in fs
        return False

    out: Dict[str, Any] = {"StashConfig": {"Name": sc.Name}}

    # Preserve top-level Retry if present (even if explicitly null)
    if _provided(sc, 'RetryCfg'):
        if sc.RetryCfg is None:
            out["StashConfig"]["Retry"] = None
        else:
            out["StashConfig"]["Retry"] = sc.RetryCfg.model_dump(by_alias=True, exclude_none=True)

    # It can be useful to keep Defaults/Forced as-is for reference
    if defaults is not None:
        d: Dict[str, Any] = {}
        if defaults.URLRoot is not None:
            d["URLRoot"] = defaults.URLRoot
        if defaults.Headers is not None:
            d["Headers"] = _copy_map(defaults.Headers)
        if defaults.Body is not None:
            d["Body"] = _copy_map(defaults.Body)
        if defaults.Query is not None:
            d["Query"] = _copy_map(defaults.Query)
        if _provided(defaults, 'RetryCfg'):
            if defaults.RetryCfg is None:
                d["Retry"] = None
            else:
                d["Retry"] = defaults.RetryCfg.model_dump(by_alias=True, exclude_none=True)
        if d:
            out["StashConfig"]["Defaults"] = d

    if forced is not None:
        f: Dict[str, Any] = {}
        if forced.URLRoot is not None:
            f["URLRoot"] = forced.URLRoot
        if forced.Headers is not None:
            f["Headers"] = _copy_map(forced.Headers)
        if forced.Body is not None:
            f["Body"] = _copy_map(forced.Body)
        if forced.Query is not None:
            f["Query"] = _copy_map(forced.Query)
        if _provided(forced, 'RetryCfg'):
            # Generally Forced.Retry is not expected; but if provided, include for transparency (including explicit null)
            if forced.RetryCfg is None:
                f["Retry"] = None
            else:
                f["Retry"] = forced.RetryCfg.model_dump(by_alias=True, exclude_none=True)
        if f:
            out["StashConfig"]["Forced"] = f

    # Sequences with resolved requests
    seq_list: List[Dict[str, Any]] = []
    for seq in sc.Sequences:
        seq_out: Dict[str, Any] = {
            "Name": seq.Name,
            "Type": seq.Type.value,
        }
        if seq.ConcurrencyLimit is not None:
            seq_out["ConcurrencyLimit"] = seq.ConcurrencyLimit

        resolved_requests: List[Dict[str, Any]] = []
        for item in seq.Requests:
            req = item.value

            # base sections per rules
            headers = _copy_map(req.Headers) if req.Headers is not None else _copy_map(defaults.Headers) if (defaults and defaults.Headers is not None) else None
            body = _copy_map(req.Body) if req.Body is not None else _copy_map(defaults.Body) if (defaults and defaults.Body is not None) else None
            query = _copy_map(req.Query) if req.Query is not None else _copy_map(defaults.Query) if (defaults and defaults.Query is not None) else None

            # overlay forced last
            if forced is not None and forced.Headers is not None:
                headers = headers or {}
                headers.update(forced.Headers)
            if forced is not None and forced.Body is not None:
                body = body or {}
                body.update(forced.Body)
            if forced is not None and forced.Query is not None:
                query = query or {}
                query.update(forced.Query)

            # resolve retry precedence with explicit-null awareness
            retry_set = False
            retry_value: Optional[Retry] = None

            if _provided(req, 'RetryCfg'):
                retry_set = True
                retry_value = req.RetryCfg  # may be None
            elif defaults is not None and _provided(defaults, 'RetryCfg'):
                retry_set = True
                retry_value = defaults.RetryCfg
            elif _provided(sc, 'RetryCfg'):
                retry_set = True
                retry_value = sc.RetryCfg

            req_out: Dict[str, Any] = {
                item.key: {
                    "Method": req.Method.value,
                    "URLPath": req.URLPath,
                }
            }
            inner = req_out[item.key]
            if headers is not None:
                inner["Headers"] = headers
            if body is not None:
                inner["Body"] = body
            if query is not None:
                inner["Query"] = query
            if req.TimeoutSeconds is not None:
                inner["TimeoutSeconds"] = req.TimeoutSeconds

            if retry_set:
                if retry_value is None:
                    inner["Retry"] = None
                else:
                    inner["Retry"] = retry_value.model_dump(by_alias=True, exclude_none=True)

            resolved_requests.append(req_out)

        seq_out["Requests"] = resolved_requests
        seq_list.append(seq_out)

    out["StashConfig"]["Sequences"] = seq_list
    return out

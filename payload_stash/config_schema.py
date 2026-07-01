from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union, Tuple

import yaml
from typing_extensions import Annotated
from pydantic import BaseModel, Field, ValidationError, ConfigDict, model_validator, field_validator, TypeAdapter

from . import config_utility as cfgutil


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


class AmqpDeliveryMode(str, Enum):
    transient = "transient"
    persistent = "persistent"


class AmqpProperties(BaseModel):
    model_config = ConfigDict(extra='forbid', use_enum_values=True)

    ContentType: Optional[Any] = None
    ContentEncoding: Optional[Any] = None
    DeliveryMode: Optional[AmqpDeliveryMode] = None
    Priority: Optional[int] = Field(None, ge=0, le=9)
    CorrelationId: Optional[Any] = None
    ReplyTo: Optional[Any] = None
    Expiration: Optional[Any] = None
    MessageId: Optional[Any] = None
    Type: Optional[Any] = None
    AppId: Optional[Any] = None
    # AMQP application headers (the message's header table)
    Headers: Optional[Dict[str, Any]] = None


class AmqpTLS(BaseModel):
    """TLS settings for amqps:// brokers. Only applied when the URI scheme is amqps."""
    model_config = ConfigDict(extra='forbid')

    CAFile: Optional[str] = None       # PEM file of CA cert(s) used to verify the broker
    CAPath: Optional[str] = None       # directory of CA certs (hashed OpenSSL layout)
    CertFile: Optional[str] = None     # client certificate (PEM) for mutual TLS
    KeyFile: Optional[str] = None      # client private key (PEM) for mutual TLS
    VerifyPeer: Optional[bool] = None  # default True; when False, skip cert/hostname verification
    ServerName: Optional[str] = None   # SNI / hostname to verify against (defaults to the URI host)


class WaitForMode(str, Enum):
    rpc = "rpc"
    subscribe = "subscribe"


class AmqpWaitFor(BaseModel):
    """Publish, then await a response message (one atomic operation). Two modes:
    - rpc: await a correlated reply on an auto reply-to queue (reply_to + correlation_id).
    - subscribe: bind a temp queue to an exchange (before publishing) and await a message
      satisfying the `Match` predicate (an Expect-style list evaluated against each message).
    """
    model_config = ConfigDict(extra='forbid', use_enum_values=True)

    Mode: WaitForMode
    TimeoutSeconds: Optional[float] = Field(None, ge=0)  # falls back to FlowControl.TimeoutSeconds
    # subscribe-only fields:
    Exchange: Optional[str] = None
    RoutingKey: Optional[str] = None
    Match: Optional[List[Dict[str, Any]]] = None

    @model_validator(mode='after')
    def _check_mode(self) -> 'AmqpWaitFor':
        if self.Mode == "rpc":
            extra = [f for f in ("Exchange", "RoutingKey", "Match") if getattr(self, f) is not None]
            if extra:
                raise ValueError(f"WaitFor Mode 'rpc' does not use {extra} (those belong to Mode 'subscribe')")
        elif self.Mode == "subscribe":
            if not (isinstance(self.Exchange, str) and self.Exchange.strip()):
                raise ValueError("WaitFor Mode 'subscribe' requires a non-empty Exchange to bind the temp queue to")
            if not self.Match:
                raise ValueError("WaitFor Mode 'subscribe' requires a non-empty Match predicate list")
        return self


class AmqpSection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    URI: Optional[str] = None
    Exchange: Optional[str] = None
    RoutingKey: Optional[str] = None
    Confirm: Optional[bool] = None
    Mandatory: Optional[bool] = None
    TLS: Optional[AmqpTLS] = None
    WaitFor: Optional[AmqpWaitFor] = None
    Properties: Optional[AmqpProperties] = None


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


class FlowControlCfg(BaseModel):
    model_config = ConfigDict(extra='forbid')
    DelaySeconds: Optional[int] = Field(None, ge=0)
    TimeoutSeconds: Optional[int] = Field(None, ge=0)


class DefaultsSection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    # URLRoot is required only when at least one HTTP request is present (enforced in StashConfig).
    URLRoot: Optional[str] = None
    FlowControl: FlowControlCfg

    # Optional Defaults
    InsecureTLS: Optional[bool] = None
    Headers: Optional[Dict[str, Any]] = None
    Body: Optional[Dict[str, Any]] = None
    Query: Optional[Dict[str, Any]] = None
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')
    Response: Optional[ResponseCfg] = None
    AMQP: Optional[AmqpSection] = None


class ForcedSection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Headers: Optional[Dict[str, Any]] = None
    Body: Optional[Dict[str, Any]] = None
    Query: Optional[Dict[str, Any]] = None
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')
    AMQP: Optional[AmqpSection] = None


class ResponseCfg(BaseModel):
    model_config = ConfigDict(extra='forbid')
    PrettyPrint: Optional[bool] = None
    Sort: Optional[bool] = None


class HttpRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Transport: Literal["http"] = "http"
    Method: Method
    URLPath: str
    Headers: Optional[Dict[str, Any]] = None
    Body: Optional[Dict[str, Any]] = None
    Query: Optional[Dict[str, Any]] = None
    FlowControl: Optional[FlowControlCfg] = None
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')
    Response: Optional[ResponseCfg] = None
    InsecureTLS: Optional[bool] = None
    Capture: Optional[Dict[str, Any]] = None
    Expect: Optional[List[Dict[str, Any]]] = None
    dynamics: Optional[Dynamics] = None


class AmqpRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Transport: Literal["amqp"]
    AMQP: AmqpSection
    Body: Optional[Dict[str, Any]] = None
    FlowControl: Optional[FlowControlCfg] = None
    RetryCfg: Optional[Retry] = Field(None, alias='Retry')
    Capture: Optional[Dict[str, Any]] = None
    Expect: Optional[List[Dict[str, Any]]] = None
    dynamics: Optional[Dynamics] = None


class RequestItem(BaseModel):
    """Represents one mapping item in Requests list: { <Key>: <Request> }"""

    key: str
    value: Union[HttpRequest, AmqpRequest]

    @classmethod
    def from_mapping(cls, m: Dict[str, Any]) -> "RequestItem":
        if not isinstance(m, dict) or len(m) != 1:
            raise ValueError("Each Requests entry must be a single-key mapping: { <Key>: {Request...} }")
        k, v = next(iter(m.items()))
        if not isinstance(v, dict):
            raise ValueError("Each Requests entry value must be a mapping of request fields")
        v = dict(v)
        # Default the transport discriminator so existing HTTP configs (no Transport key) validate unchanged.
        v.setdefault("Transport", "http")
        req = _REQUEST_ADAPTER.validate_python(v)
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

    @model_validator(mode='after')
    def check_unique_request_keys(self) -> 'Sequence':
        # Ensure request keys within this sequence are unique
        keys = [item.key for item in self.Requests]
        seen = set()
        dups: list[str] = []
        for k in keys:
            if k in seen and k not in dups:
                dups.append(k)
            seen.add(k)
        if dups:
            raise ValueError(
                f"Duplicate request keys are not allowed within a sequence. Duplicates found: {dups}"
            )
        return self


class StashConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    Name: str
    Defaults: DefaultsSection
    Forced: Optional[ForcedSection] = None
    Sequences: List[Sequence]

    @model_validator(mode='after')
    def check_defaults_urlroot(self) -> 'StashConfig':
        # Enforce that Defaults.FlowControl has both fields (at least require presence, values validated by FlowControlCfg)
        if self.Defaults is None or self.Defaults.FlowControl is None:
            raise ValueError("Defaults.FlowControl is required with DelaySeconds and TimeoutSeconds integers")
        # URLRoot is required only when at least one HTTP request is present.
        has_http = any(
            getattr(item.value, "Transport", "http") == "http"
            for seq in self.Sequences for item in seq.Requests
        )
        if has_http and (not isinstance(self.Defaults.URLRoot, str) or not self.Defaults.URLRoot.strip()):
            raise ValueError("Defaults.URLRoot is required and must be a non-empty string when HTTP requests are present")
        return self

    @model_validator(mode='after')
    def check_amqp_requests(self) -> 'StashConfig':
        # For every AMQP request, ensure a broker URI is resolvable and that at least one of
        # Exchange/RoutingKey is non-empty (both empty publishes to the default exchange with an
        # empty routing key, which goes nowhere). Precedence mirrors the section merge: Forced > request > Defaults.
        d_amqp = self.Defaults.AMQP if self.Defaults else None
        f_amqp = self.Forced.AMQP if self.Forced else None

        def _eff(field: str, r_amqp):
            for sec in (f_amqp, r_amqp, d_amqp):
                if sec is not None:
                    val = getattr(sec, field, None)
                    if val is not None:
                        return val
            return None

        for seq in self.Sequences:
            for item in seq.Requests:
                req = item.value
                if getattr(req, "Transport", "http") != "amqp":
                    continue
                r_amqp = req.AMQP
                uri = _eff("URI", r_amqp)
                if not (isinstance(uri, str) and uri.strip()):
                    raise ValueError(
                        f"AMQP request '{item.key}' has no broker URI: set AMQP.URI on the request or Defaults.AMQP.URI"
                    )
                exchange = _eff("Exchange", r_amqp)
                routing_key = _eff("RoutingKey", r_amqp)
                if not (exchange and str(exchange).strip()) and not (routing_key and str(routing_key).strip()):
                    raise ValueError(
                        f"AMQP request '{item.key}' must set a non-empty AMQP.Exchange or AMQP.RoutingKey"
                    )
        return self

    @model_validator(mode='after')
    def check_unique_sequence_names(self) -> 'StashConfig':
        # Ensure sequence names are unique across the config
        names = [seq.Name for seq in self.Sequences]
        seen = set()
        dups: list[str] = []
        for n in names:
            if n in seen and n not in dups:
                dups.append(n)
            seen.add(n)
        if dups:
            raise ValueError(
                f"Duplicate sequence names are not allowed. Duplicates found: {dups}"
            )
        return self


class DynamicPattern(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template: str


class Dynamics(BaseModel):
    model_config = ConfigDict(extra='forbid')
    patterns: Dict[str, DynamicPattern]
    sets: Optional[Dict[str, List[str]]] = None


class TopLevelConfig(BaseModel):
    """Top-level model. Allows extra keys (anchors/aliases) but requires StashConfig."""

    model_config = ConfigDict(extra='allow')

    StashConfig: StashConfig
    dynamics: Optional[Dynamics] = Field(None, alias='dynamics')


def validate_config_data(data: Dict[str, Any]) -> TopLevelConfig:
    """Validate already-loaded YAML data against the schema.

    Returns the parsed TopLevelConfig or raises ValidationError.
    Additionally, provides a friendlier message if the top-level `StashConfig`
    section is missing but common StashConfig children are present at the root.
    """
    # Normalize alternate capitalization for dynamics
    if isinstance(data, dict) and 'dynamics' not in data and 'Dynamics' in data:
        data = dict(data)
        data['dynamics'] = data.get('Dynamics')

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


def _resolve_func_obj(obj: Dict[str, Any]) -> Any:
    """
    Evaluate a special function-call object embedded in YAML sections.
    Supported forms:
      - {"$func": "timestamp", "format": "iso_8601", "when": "resolve|request"}
      - {"$timestamp": "epoch_ms"}
      - {"$timestamp": {"format": "epoch_ms", "when": "request"}}
    If when == "request", return a deferred marker that can be resolved later using
    cfgutil.resolve_deferred at request time.
    """
    # Normalize different syntaxes into (func, params, when)
    func_name: Optional[str] = None
    params: Dict[str, Any] = {}
    when: str = "resolve"

    if "$func" in obj:
        func_name = obj.get("$func")
        # pull params except special keys
        for k, v in obj.items():
            if k not in {"$func", "when"}:
                params[k] = v
        when = obj.get("when", "resolve")
    elif "$timestamp" in obj:
        func_name = "timestamp"
        ts_val = obj.get("$timestamp")
        if isinstance(ts_val, dict):
            params.update({k: v for k, v in ts_val.items() if k != "when"})
            when = ts_val.get("when", obj.get("when", "resolve"))
        else:
            params["format"] = ts_val or "iso_8601"
            when = obj.get("when", "resolve")
    else:
        # Not a function object
        return obj

    # Defaults/aliases for timestamp
    if func_name == "timestamp":
        fmt = params.get("format") or params.get("fmt") or "iso_8601"
        if when == "request":
            # Return a deferred marker that downstream can evaluate
            return {"$deferred": {"func": "timestamp", "format": fmt}}
        # resolve immediately
        return cfgutil.timestamp(fmt)

    raise ValueError(f"Unknown function in config: {func_name}")


def _resolve_dynamic_obj(obj: Dict[str, Any], dyn: Optional[Dynamics], secrets: Optional[Dict[str, str]] = None, redact_secrets: bool = False, resolved_cache: Optional[Dict[str, Any]] = None) -> Any:
    """
    Evaluate a $dynamic object using the provided dynamics context.
    Forms:
      - {"$dynamic": "patternName"}
      - {"$dynamic": "patternName", "when": "resolve|request"}
    """
    if "$dynamic" not in obj:
        return obj
    if dyn is None:
        raise ValueError("$dynamic used but no top-level 'dynamics' section was provided")
    pattern_name = obj.get("$dynamic")
    when = obj.get("when", "resolve")
    if not isinstance(pattern_name, str):
        raise ValueError("$dynamic must be a string naming a pattern")
    pat = dyn.patterns.get(pattern_name)
    if pat is None:
        raise ValueError(f"Unknown dynamic pattern: {pattern_name}")
    template = pat.template
    sets = dyn.sets or {}
    if when == "request":
        # Validate template now to ensure secrets/sets are valid, but keep as deferred for request-time materialization
        try:
            cfgutil.dynamic_expand(template, sets, secrets=secrets, redact_secrets=True)
        except Exception as e:
            # Re-raise to fail validation early with informative message
            raise e
        return {"$deferred": {"dynamic": {"template": template, "sets": sets}}}
    # resolve now: use precomputed cache if available to ensure a single value per pattern per resolved file
    if resolved_cache is not None:
        if pattern_name in resolved_cache:
            return resolved_cache[pattern_name]
        # If not precomputed, compute and store (fallback safety)
        resolved_cache[pattern_name] = cfgutil.dynamic_expand(template, sets, secrets=secrets, redact_secrets=redact_secrets)
        return resolved_cache[pattern_name]
    return cfgutil.dynamic_expand(template, sets, secrets=secrets, redact_secrets=redact_secrets)


def _resolve_values(value: Any, dyn: Optional[Dynamics], secrets: Optional[Dict[str, str]] = None, redact_secrets: bool = False, resolved_cache: Optional[Dict[str, Any]] = None) -> Any:
    """Recursively resolve any function-call, $dynamic objects, and $secrets references.

    - Supports mapping form: {"$secrets": "keyName"}
    - Supports inline string form: "... { $secrets: keyName } ..."
    - When redact_secrets is True, any resolved secret values are replaced with "***REDACTED***" in the returned structure.
    - If a secret is requested but no secrets were provided, raises a ValueError.
    """
    # Helper for inline secret replacement inside strings
    def _replace_inline_secrets(s: str) -> str:
        import re as _re
        pattern = _re.compile(r"\{\s*\$secrets\s*:\s*([A-Za-z0-9_\-\.]+)\s*\}")
        def _rep(m):
            key = m.group(1)
            if secrets is None:
                raise ValueError(f"Secret '{key}' requested but no --secrets file was provided")
            if key not in secrets:
                raise ValueError(f"Unknown secret requested: '{key}'")
            return "***REDACTED***" if redact_secrets else str(secrets[key])
        return pattern.sub(_rep, s)

    if isinstance(value, dict):
        # Don't touch already-deferred nodes
        if "$deferred" in value:
            return value
        # Mapping form for secrets
        if "$secrets" in value:
            skey = value.get("$secrets")
            if not isinstance(skey, str):
                raise ValueError("$secrets must be used as a string key name, e.g., { $secrets: my_key }")
            if secrets is None:
                raise ValueError(f"Secret '{skey}' requested but no --secrets file was provided")
            if skey not in secrets:
                raise ValueError(f"Unknown secret requested: '{skey}'")
            return "***REDACTED***" if redact_secrets else str(secrets[skey])
        # Check if this dict itself is a function-call object
        if "$func" in value or "$timestamp" in value:
            return _resolve_func_obj(value)
        # Check if it's a dynamic object
        if "$dynamic" in value:
            return _resolve_dynamic_obj(value, dyn, secrets, redact_secrets, resolved_cache)
        # $pattern — inline template, always request-time. Validate the template now
        # so errors surface at config-load time, but defer expansion to request time
        # so that ${captured:KEY} and other runtime values are available.
        if "$pattern" in value:
            template = value["$pattern"]
            if not isinstance(template, str):
                raise ValueError("$pattern value must be a string template")
            sets = dyn.sets if dyn else {}
            try:
                cfgutil.dynamic_expand(template, sets or {}, secrets=secrets, redact_secrets=True)
            except Exception as e:
                raise e
            return {"$deferred": {"pattern": {"template": template, "sets": dict(sets or {})}}}
        # Else resolve each entry
        return {k: _resolve_values(v, dyn, secrets, redact_secrets, resolved_cache) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_values(v, dyn, secrets, redact_secrets, resolved_cache) for v in value]
    if isinstance(value, str):
        return _replace_inline_secrets(value)
    # primitives unchanged
    return value


def _amqp_section_to_dict(sec: Any) -> Dict[str, Any]:
    if sec is None:
        return {}
    try:
        return sec.model_dump(by_alias=True, exclude_none=True)
    except Exception:
        return {}


def _merge_amqp_dict(d_sec: Any, r_sec: Any, f_sec: Any) -> Dict[str, Any]:
    """Merge AMQP sections with precedence Defaults < request < Forced; deep-merge Properties(.Headers)."""
    out: Dict[str, Any] = {}
    for layer in (_amqp_section_to_dict(d_sec), _amqp_section_to_dict(r_sec), _amqp_section_to_dict(f_sec)):
        for k, v in layer.items():
            if k == "Properties" and isinstance(v, dict) and isinstance(out.get("Properties"), dict):
                props = dict(out["Properties"])
                for pk, pv in v.items():
                    if pk == "Headers" and isinstance(pv, dict) and isinstance(props.get("Headers"), dict):
                        merged_h = dict(props["Headers"]); merged_h.update(pv); props["Headers"] = merged_h
                    else:
                        props[pk] = pv
                out["Properties"] = props
            else:
                out[k] = v
    return out


# Ensure forward references are resolved for models that refer to each other
try:
    # In Pydantic v2, model_rebuild resolves forward refs
    ns = globals()
    for _model in (AmqpProperties, AmqpTLS, AmqpWaitFor, AmqpSection, HttpRequest, AmqpRequest, RequestItem, Sequence, DefaultsSection, ForcedSection, StashConfig, TopLevelConfig):
        _model.model_rebuild(force=True, _types_namespace=ns)
except Exception:
    # Safe to ignore if rebuild not necessary
    pass


# Discriminated union over the request transport. Built after model_rebuild so all forward refs
# (e.g. Dynamics) are resolved. Used by RequestItem.from_mapping.
RequestModel = Annotated[Union[HttpRequest, AmqpRequest], Field(discriminator="Transport")]
_REQUEST_ADAPTER = TypeAdapter(RequestModel)


def build_resolved_config_dict(cfg: TopLevelConfig, secrets: Optional[Dict[str, str]] = None, redact_secrets: bool = False) -> Dict[str, Any]:
    """Build a fully-resolved config dict with Defaults and Forced applied into each Request.

    Rules:
    - For sections Headers/Body/Query: use request section if present, else Defaults.section; then overlay Forced.section.
    - Retry precedence respects explicit nulls: request.Retry (even null) > Defaults.Retry (even null).
      Only fall through when a level omits the Retry field entirely.
    - Anchors are already resolved by yaml.safe_load; we also ensure the resulting dict contains plain maps.
    """
    sc = cfg.StashConfig
    defaults = sc.Defaults
    forced = sc.Forced

    dyn = getattr(cfg, 'dynamics', None)

    # Precompute resolve-time dynamic values once per config to ensure consistency across requests
    resolved_dyn_cache: Optional[Dict[str, Any]] = None
    if dyn is not None:
        resolved_dyn_cache = {}
        sets = dyn.sets or {}
        for name, pat in dyn.patterns.items():
            # Compute a single value per pattern for this resolved file
            resolved_dyn_cache[name] = cfgutil.dynamic_expand(pat.template, sets, secrets=secrets, redact_secrets=redact_secrets)

    # Helper to detect if a Pydantic field was provided (even if its value is None)
    def _provided(m: Any, field_name: str) -> bool:
        try:
            fs = getattr(m, 'model_fields_set')
        except Exception:
            fs = None
        if isinstance(fs, set):
            return field_name in fs
        return False

    sc_out: Dict[str, Any] = {"Name": sc.Name}


    # It can be useful to keep Defaults/Forced as-is for reference
    if defaults is not None:
        d: Dict[str, Any] = {}
        if defaults.URLRoot is not None:
            d["URLRoot"] = defaults.URLRoot
        if defaults.FlowControl is not None:
            fc: Dict[str, Any] = {}
            if defaults.FlowControl.DelaySeconds is not None:
                fc["DelaySeconds"] = defaults.FlowControl.DelaySeconds
            if defaults.FlowControl.TimeoutSeconds is not None:
                fc["TimeoutSeconds"] = defaults.FlowControl.TimeoutSeconds
            d["FlowControl"] = fc
        if defaults.Headers is not None:
            d["Headers"] = _resolve_values(_copy_map(defaults.Headers), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if defaults.Body is not None:
            d["Body"] = _resolve_values(_copy_map(defaults.Body), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if defaults.Query is not None:
            d["Query"] = _resolve_values(_copy_map(defaults.Query), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if _provided(defaults, 'RetryCfg'):
            if defaults.RetryCfg is None:
                d["Retry"] = None
            else:
                d["Retry"] = defaults.RetryCfg.model_dump(by_alias=True, exclude_none=True)
        if defaults.Response is not None:
            d["Response"] = defaults.Response.model_dump(exclude_none=True)
        # Include InsecureTLS only if provided; effective default is False when omitted
        if _provided(defaults, 'InsecureTLS') and defaults.InsecureTLS is not None:
            d["InsecureTLS"] = bool(defaults.InsecureTLS)
        if d:
            sc_out["Defaults"] = d

    if forced is not None:
        f: Dict[str, Any] = {}
        if forced.Headers is not None:
            f["Headers"] = _resolve_values(_copy_map(forced.Headers), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if forced.Body is not None:
            f["Body"] = _resolve_values(_copy_map(forced.Body), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if forced.Query is not None:
            f["Query"] = _resolve_values(_copy_map(forced.Query), dyn, secrets, redact_secrets, resolved_dyn_cache)
        if _provided(forced, 'RetryCfg'):
            # Generally Forced.Retry is not expected; but if provided, include for transparency (including explicit null)
            if forced.RetryCfg is None:
                f["Retry"] = None
            else:
                f["Retry"] = forced.RetryCfg.model_dump(by_alias=True, exclude_none=True)
        if f:
            sc_out["Forced"] = f


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

            # If this request defines its own dynamics, merge them with the top-level dynamics.
            # Request-level patterns override top-level patterns of the same name; sets are merged.
            # This allows one-off generators without polluting the top-level dynamics section.
            req_dyn = req.dynamics
            if req_dyn is not None:
                merged_patterns = {**(dyn.patterns if dyn else {}), **req_dyn.patterns}
                merged_sets = {**(dyn.sets or {} if dyn else {}), **(req_dyn.sets or {})}
                eff_dyn = Dynamics(patterns=merged_patterns, sets=merged_sets or None)
                # Build a resolve-time cache that starts from the top-level cache and adds local patterns
                eff_cache: Optional[Dict[str, Any]] = dict(resolved_dyn_cache or {})
                for name, pat in req_dyn.patterns.items():
                    eff_cache[name] = cfgutil.dynamic_expand(pat.template, merged_sets, secrets=secrets, redact_secrets=redact_secrets)
            else:
                eff_dyn = dyn
                eff_cache = resolved_dyn_cache

            # AMQP transport: emit a distinct resolved block. HTTP-only sections (URLRoot/Headers/
            # Query/InsecureTLS/Response) are intentionally skipped; Body/Retry/FlowControl are shared.
            if getattr(req, "Transport", "http") == "amqp":
                a_body = _copy_map(req.Body) if req.Body is not None else (_copy_map(defaults.Body) if (defaults and defaults.Body is not None) else None)
                if forced is not None and forced.Body is not None:
                    a_body = a_body or {}
                    a_body.update(forced.Body)
                a_body = _resolve_values(a_body, eff_dyn, secrets, redact_secrets, eff_cache) if a_body is not None else None

                amqp_merged = _merge_amqp_dict(defaults.AMQP if defaults else None, req.AMQP, forced.AMQP if forced else None)
                amqp_resolved = _resolve_values(amqp_merged, eff_dyn, secrets, redact_secrets, eff_cache)

                a_retry_set = False
                a_retry_value: Optional[Retry] = None
                if _provided(req, 'RetryCfg'):
                    a_retry_set = True
                    a_retry_value = req.RetryCfg
                elif defaults is not None and _provided(defaults, 'RetryCfg'):
                    a_retry_set = True
                    a_retry_value = defaults.RetryCfg

                req_out_amqp: Dict[str, Any] = {item.key: {"Transport": "amqp", "AMQP": amqp_resolved}}
                inner_amqp = req_out_amqp[item.key]
                if a_body is not None:
                    inner_amqp["Body"] = a_body
                a_fc: Dict[str, Any] = {}
                if defaults and defaults.FlowControl is not None:
                    if defaults.FlowControl.DelaySeconds is not None:
                        a_fc["DelaySeconds"] = defaults.FlowControl.DelaySeconds
                    if defaults.FlowControl.TimeoutSeconds is not None:
                        a_fc["TimeoutSeconds"] = defaults.FlowControl.TimeoutSeconds
                if req.FlowControl is not None:
                    if req.FlowControl.DelaySeconds is not None:
                        a_fc["DelaySeconds"] = req.FlowControl.DelaySeconds
                    if req.FlowControl.TimeoutSeconds is not None:
                        a_fc["TimeoutSeconds"] = req.FlowControl.TimeoutSeconds
                if a_fc:
                    inner_amqp["FlowControl"] = a_fc
                if a_retry_set:
                    inner_amqp["Retry"] = None if a_retry_value is None else a_retry_value.model_dump(by_alias=True, exclude_none=True)
                if req.Capture is not None:
                    inner_amqp["Capture"] = req.Capture
                if req.Expect is not None:
                    inner_amqp["Expect"] = _resolve_values(req.Expect, eff_dyn, secrets, redact_secrets, eff_cache)
                resolved_requests.append(req_out_amqp)
                continue

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

            # resolve any function-call or dynamic objects after merges
            headers = _resolve_values(headers, eff_dyn, secrets, redact_secrets, eff_cache) if headers is not None else None
            body = _resolve_values(body, eff_dyn, secrets, redact_secrets, eff_cache) if body is not None else None
            query = _resolve_values(query, eff_dyn, secrets, redact_secrets, eff_cache) if query is not None else None

            # resolve retry precedence with explicit-null awareness
            retry_set = False
            retry_value: Optional[Retry] = None

            if _provided(req, 'RetryCfg'):
                retry_set = True
                retry_value = req.RetryCfg  # may be None
            elif defaults is not None and _provided(defaults, 'RetryCfg'):
                retry_set = True
                retry_value = defaults.RetryCfg

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
            # Include Response block if provided; else inherit from Defaults if present
            if req.Response is not None:
                inner["Response"] = req.Response.model_dump(exclude_none=True)
            elif defaults is not None and defaults.Response is not None:
                inner["Response"] = defaults.Response.model_dump(exclude_none=True)
            # Always include effective URLRoot from Defaults
            if defaults and defaults.URLRoot:
                inner["URLRoot"] = defaults.URLRoot
            # Include effective FlowControl (Defaults overridden by per-request)
            fc_eff: Dict[str, Any] = {}
            if defaults and defaults.FlowControl is not None:
                if defaults.FlowControl.DelaySeconds is not None:
                    fc_eff["DelaySeconds"] = defaults.FlowControl.DelaySeconds
                if defaults.FlowControl.TimeoutSeconds is not None:
                    fc_eff["TimeoutSeconds"] = defaults.FlowControl.TimeoutSeconds
            if req.FlowControl is not None:
                if req.FlowControl.DelaySeconds is not None:
                    fc_eff["DelaySeconds"] = req.FlowControl.DelaySeconds
                if req.FlowControl.TimeoutSeconds is not None:
                    fc_eff["TimeoutSeconds"] = req.FlowControl.TimeoutSeconds
            if fc_eff:
                inner["FlowControl"] = fc_eff

            # Effective InsecureTLS: default False; Defaults.InsecureTLS if provided; overridden by request-level if provided
            insecure_eff = False
            if defaults is not None and getattr(defaults, 'InsecureTLS', None) is not None:
                insecure_eff = bool(defaults.InsecureTLS)
            if getattr(req, 'InsecureTLS', None) is not None:
                insecure_eff = bool(req.InsecureTLS)
            inner["InsecureTLS"] = bool(insecure_eff)

            if retry_set:
                if retry_value is None:
                    inner["Retry"] = None
                else:
                    inner["Retry"] = retry_value.model_dump(by_alias=True, exclude_none=True)

            if req.Capture is not None:
                inner["Capture"] = req.Capture
            if req.Expect is not None:
                inner["Expect"] = _resolve_values(req.Expect, eff_dyn, secrets, redact_secrets, eff_cache)

            resolved_requests.append(req_out)

        seq_out["Requests"] = resolved_requests
        seq_list.append(seq_out)

    sc_out["Sequences"] = seq_list

    # Build final output with 'Static Dynamics' at the top, then StashConfig
    final_out: Dict[str, Any] = {}
    if resolved_dyn_cache is not None and len(resolved_dyn_cache) > 0:
        final_out["Static Dynamics"] = resolved_dyn_cache
    final_out["StashConfig"] = sc_out

    return final_out

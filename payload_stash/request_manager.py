"""
request_manager.py

Centralized HTTP request handling with retries and backoff for PayloadStash.

Design:
- Use urllib3 PoolManager for connection pooling, but disable its automatic retry/sleeping.
- Implement per-request retry behavior (fixed/exponential backoff, jitter, status/exception based) in this module
  to match the config schema.

This module exposes a RequestManager class with a simple `request` method,
returning (status_code, headers_dict, response_text).
"""
from __future__ import annotations

from typing import Dict, Tuple, Optional, Any, Iterable
import time
import random

import urllib3
from urllib3 import exceptions as u3exc


# Exception groups we may treat as retryable based on config
_TIMEOUT_EXCS: tuple[type[BaseException], ...] = (
    u3exc.ReadTimeoutError,
    u3exc.ConnectTimeoutError,
)
_NETWORK_EXCS: tuple[type[BaseException], ...] = (
    u3exc.ProtocolError,
    u3exc.NewConnectionError,
    u3exc.NameResolutionError if hasattr(u3exc, "NameResolutionError") else Exception,
)


class RequestManager:
    def __init__(
        self,
        pool_maxsize: int = 50,
        num_pools: int = 10,
    ) -> None:
        # Disable urllib3 warnings about insecure requests not relevant here
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Disable internal retries; we fully control retries/backoff per call
        self._pool = urllib3.PoolManager(
            retries=False,
            num_pools=num_pools,
            maxsize=pool_maxsize,
        )

    def _single_attempt(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]],
        body: Optional[bytes],
        timeout_s: Optional[float],
    ) -> Tuple[int, Dict[str, str], str]:
        timeout = None
        if isinstance(timeout_s, (int, float)) and timeout_s > 0:
            timeout = urllib3.Timeout(total=float(timeout_s))
        # Make the request; urllib3 returns HTTPResponse
        resp = self._pool.request(
            method=method.upper(),
            url=url,
            body=body,
            headers=headers or {},
            timeout=timeout,
            preload_content=False,  # so we can control read
        )
        try:
            status = int(resp.status)
            # headers: HTTPHeaderDict -> convert to plain dict (last value wins)
            resp_headers = {k: v for k, v in resp.headers.items()}
            data = resp.read() or b""
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = str(data)
            return status, resp_headers, text
        finally:
            try:
                resp.close()
            except Exception:
                pass

    @staticmethod
    def _compute_delay(attempt_idx: int, strategy: str, base: float, mult: float, max_backoff: Optional[float], jitter: Optional[str | bool]) -> float:
        # attempt_idx: 1-based index of the retry (1 for first retry)
        if base is None:
            base = 0.0
        if mult is None:
            mult = 2.0
        if strategy == "fixed":
            delay = base
        else:
            # exponential: base * mult^(attempt_idx-1)
            delay = base * (mult ** (attempt_idx - 1))
        if max_backoff is not None:
            delay = min(delay, max_backoff)
        # Jitter handling
        if jitter is True or (isinstance(jitter, str) and jitter.lower() == "full"):
            delay = random.uniform(0, max(delay, 0.0))
        return max(0.0, float(delay))

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout_s: Optional[float] = None,
        retry_cfg: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, str], str]:
        """
        Perform an HTTP request with schema-driven retries and backoff.

        Returns a tuple: (status_code, headers_dict, response_text)
        """
        # Fast path: no retry configured
        if not retry_cfg:
            return self._single_attempt(method, url, headers, body, timeout_s)

        # Map config -> policy with defaults
        attempts: int = int(retry_cfg.get("Attempts", 1))
        if attempts < 1:
            attempts = 1
        strategy: str = str(retry_cfg.get("BackoffStrategy", "exponential")).lower()
        base: float = float(retry_cfg.get("BackoffSeconds", 0.0) or 0.0)
        mult: float = float(retry_cfg.get("Multiplier", 2.0) or 2.0)
        max_backoff: Optional[float] = retry_cfg.get("MaxBackoffSeconds")
        max_backoff = float(max_backoff) if max_backoff is not None else None
        max_elapsed: Optional[float] = retry_cfg.get("MaxElapsedSeconds")
        max_elapsed = float(max_elapsed) if max_elapsed is not None else None
        jitter = retry_cfg.get("Jitter")
        retry_on_status: Iterable[int] = retry_cfg.get("RetryOnStatus") or [429, 500, 502, 503, 504]
        ron_errors: Optional[bool] = retry_cfg.get("RetryOnNetworkErrors")
        ron_timeouts: Optional[bool] = retry_cfg.get("RetryOnTimeouts")
        if ron_errors is None:
            ron_errors = True
        if ron_timeouts is None:
            ron_timeouts = True

        start = time.monotonic()
        last_exc: Optional[BaseException] = None
        status: int = -1
        resp_headers: Dict[str, str] = {}
        resp_text: str = ""

        for attempt in range(1, attempts + 1):
            try:
                status, resp_headers, resp_text = self._single_attempt(method, url, headers, body, timeout_s)
                last_exc = None
            except BaseException as e:
                last_exc = e
                # Decide if exception is retryable
                is_timeout = isinstance(e, _TIMEOUT_EXCS)
                is_network = isinstance(e, _NETWORK_EXCS)
                if (is_timeout and ron_timeouts) or (is_network and ron_errors):
                    # retryable
                    pass
                else:
                    # not retryable -> raise immediately
                    raise

            # Decide whether to break or retry based on result
            should_retry = False
            if last_exc is None:
                if status in retry_on_status:
                    should_retry = True

            # If no retry needed or out of attempts, break/raise
            if (not should_retry and last_exc is None) or attempt >= attempts:
                if last_exc is not None and (attempt >= attempts):
                    # exhausted
                    raise last_exc
                return status, resp_headers, resp_text

            # Compute delay for the next retry
            next_retry_index = attempt  # 1 for first retry after attempt 1
            delay = self._compute_delay(next_retry_index, strategy, base, mult, max_backoff, jitter)

            # Enforce max elapsed budget (if configured)
            if max_elapsed is not None:
                elapsed = time.monotonic() - start
                # If waiting would exceed budget, stop now
                if elapsed + delay > max_elapsed:
                    if last_exc is not None:
                        raise last_exc
                    # Return the current (possibly error) response without waiting further
                    return status, resp_headers, resp_text

            if delay > 0:
                time.sleep(delay)

        # Fallback (should not reach)
        if last_exc is not None:
            raise last_exc
        return status, resp_headers, resp_text

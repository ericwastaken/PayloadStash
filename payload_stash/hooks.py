"""Script hooks: commands a config runs at fixed points of a run.

A config lists hooks under ``StashConfig.Hooks.BeforeAll`` / ``StashConfig.Hooks.AfterAll`` and
per sequence under ``Before``. Each entry is a command string, or a mapping
``{Command: str, TimeoutSeconds: number}``.

Commands run without a shell. The command string is split into arguments first (``shlex``),
then each argument is expanded with the same placeholder engine ``$pattern`` uses, so a
captured value containing spaces or quotes stays a single argument and never runs as shell code.
Unlike request templates, a ``${captured:KEY}`` whose key is missing (or was captured as null)
fails the hook before it starts.
"""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .config_utility import _PLACEHOLDER_RE, dynamic_expand


class HookError(Exception):
    """A hook could not be prepared: bad command or a captured value that isn't available."""


@dataclass(frozen=True)
class HookSpec:
    command: str
    timeout_s: Optional[float] = None


@dataclass(frozen=True)
class HookResult:
    exit_code: Optional[int]
    duration_ms: int
    timed_out: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and self.exit_code == 0

    def describe(self) -> str:
        if self.error is not None:
            return self.error
        if self.timed_out:
            return "timed out"
        return f"exit {self.exit_code}"


def normalize_entries(entries: Any) -> List[HookSpec]:
    """Turn a hook list from the resolved config (strings or {Command, TimeoutSeconds}) into specs."""
    specs: List[HookSpec] = []
    for entry in entries or []:
        if isinstance(entry, str):
            specs.append(HookSpec(entry))
        elif isinstance(entry, dict) and isinstance(entry.get("Command"), str):
            specs.append(HookSpec(entry["Command"], entry.get("TimeoutSeconds")))
        else:
            raise HookError(f"unsupported hook entry: {entry!r}")
    return specs


def split_command(command: str) -> List[str]:
    """Split a command string into arguments like a POSIX shell would, without running one."""
    argv = shlex.split(command)
    if not argv:
        raise ValueError("hook command is empty")
    return argv


def captured_keys(text: str) -> List[str]:
    """The keys referenced as ${captured:KEY} in text, in order of first use."""
    keys: List[str] = []
    for m in _PLACEHOLDER_RE.finditer(text):
        if m.group(1) == "captured" and m.group(2) and m.group(2) not in keys:
            keys.append(m.group(2))
    return keys


def missing_captures(argv: List[str], captures: Dict[str, Any]) -> List[str]:
    """Referenced captured keys that are absent or were captured as null."""
    missing: List[str] = []
    for arg in argv:
        for key in captured_keys(arg):
            if captures.get(key) is None and key not in missing:
                missing.append(key)
    return missing


def build_argv(command: str, captures: Dict[str, Any], *,
               sets: Optional[Dict[str, List[str]]] = None,
               secrets: Optional[Dict[str, str]] = None) -> List[str]:
    """Split first, then fill in each argument. Raises HookError if a captured value is missing."""
    argv = split_command(command)
    missing = missing_captures(argv, captures)
    if missing:
        raise HookError("captured value(s) not available: " + ", ".join(missing))
    return [dynamic_expand(arg, sets or {}, secrets=secrets, captures=captures) for arg in argv]


def _kill_process_group(proc: subprocess.Popen) -> None:
    # The hook runs in its own session, so its process group id is its pid. Killing the group
    # also stops children it started (sleep, docker, ...), not just the top-level command.
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def run_command(argv: List[str], *, cwd: Union[str, Path], timeout_s: Optional[float],
                on_line: Callable[[str], None]) -> HookResult:
    """Run argv without a shell, streaming each output line (stdout and stderr merged) to on_line."""
    t0 = time.perf_counter()

    def _elapsed_ms() -> int:
        return int(round((time.perf_counter() - t0) * 1000))

    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
    except OSError as e:
        return HookResult(None, _elapsed_ms(), error=f"could not start: {e}")

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                on_line(line.rstrip("\r\n"))
            except Exception:
                # Keep draining: a stalled reader would block the hook on a full pipe.
                pass

    reader = threading.Thread(target=_pump, name="hook-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        try:
            exit_code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc)
            exit_code = proc.wait()
    except BaseException:
        # Ctrl-C (or any other interruption): don't leave the hook running on its own.
        _kill_process_group(proc)
        proc.wait()
        raise
    reader.join()
    return HookResult(exit_code, _elapsed_ms(), timed_out=timed_out)

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union
import yaml


PathLike = Union[str, Path]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


class CaseInsensitiveDict(dict):
    """A dict with case-insensitive string key lookup that preserves original key casing.

    HTTP header names are case-insensitive (RFC 9110), but urllib3 hands back the casing the
    server actually sent. Storing headers in this mapping lets `headers.ETag`, `headers.etag`
    and `headers.ETAG` all resolve, while logs and reports still show the original casing.

    Duplicate keys differing only in case follow plain-dict semantics: the last one assigned
    wins, matching the previous `{k: v for k, v in resp.headers.items()}` behavior.
    """

    @staticmethod
    def _fold(key):
        return key.lower() if isinstance(key, str) else key

    def __init__(self, data=None, **kwargs):
        super().__init__()
        self._folded: dict = {}
        if data:
            for k, v in (data.items() if hasattr(data, "items") else data):
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def __setitem__(self, key, value):
        folded = self._fold(key)
        prior = self._folded.get(folded)
        if prior is not None and prior != key:
            # Replacing a key that differs only in case: drop the old spelling.
            super().__delitem__(prior)
        self._folded[folded] = key
        super().__setitem__(key, value)

    def __getitem__(self, key):
        return super().__getitem__(self._folded.get(self._fold(key), key))

    def __delitem__(self, key):
        actual = self._folded.pop(self._fold(key), key)
        super().__delitem__(actual)

    def __contains__(self, key):
        return self._fold(key) in self._folded

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *default):
        try:
            value = self[key]
        except KeyError:
            if default:
                return default[0]
            raise
        del self[key]
        return value

    def setdefault(self, key, default=None):
        if key in self:
            return self[key]
        self[key] = default
        return default

    def update(self, data=None, **kwargs):
        if data:
            for k, v in (data.items() if hasattr(data, "items") else data):
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def clear(self) -> None:
        super().clear()
        self._folded.clear()

    def popitem(self):
        key, value = super().popitem()
        self._folded.pop(self._fold(key), None)
        return key, value

    def __ior__(self, other):
        self.update(other)
        return self

    def copy(self) -> "CaseInsensitiveDict":
        return CaseInsensitiveDict(self)


# PyYAML dispatches representers by exact type, so a dict subclass needs its own or dumping
# a headers mapping raises RepresenterError.
def _represent_case_insensitive_dict(dumper, data):
    return dumper.represent_dict(data)


NoAliasDumper.add_representer(CaseInsensitiveDict, _represent_case_insensitive_dict)
yaml.SafeDumper.add_representer(CaseInsensitiveDict, _represent_case_insensitive_dict)
yaml.Dumper.add_representer(CaseInsensitiveDict, _represent_case_insensitive_dict)


def write_log(log_file: PathLike, message: str, newline: bool = True) -> None:
    """
    Append a message to the specified log file, creating parent directories if necessary.

    Parameters:
    - log_file: Path or string to the log file.
    - message: Text to write.
    - newline: If True, appends a trailing newline if not already present.
    """
    p = Path(log_file)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

    # Normalize newline handling
    text = message
    if newline and not message.endswith("\n"):
        text += "\n"

    with p.open('a', encoding='utf-8') as f:
        f.write(text)


def start_run_log(log_file: PathLike, ts_utc: str, sc_name: str, resolved_config_path: PathLike) -> None:
    """
    Initialize the run log with a standardized header for a PayloadStash run.

    Parameters:
    - log_file: Path to log file to append.
    - ts_utc: Timestamp string in UTC (already formatted).
    - sc_name: StashConfig name.
    - resolved_config_path: Path to the resolved config file.
    """
    write_log(log_file, f"=== PayloadStash run started at {ts_utc} UTC ===")
    write_log(log_file, f"Name: {sc_name}")
    write_log(log_file, f"Resolved config: {resolved_config_path}")
    write_log(log_file, "--- Sequences ---")


def write_yaml_file(path: PathLike, data) -> None:
    """Write YAML to a file without aliases, preserving order."""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8') as f:
        yaml.dump(data, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)


def yaml_to_string(data) -> str:
    """Return YAML string without aliases, preserving order."""
    return yaml.dump(data, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)


def log_yaml(log_file: PathLike, title: str, data, indent: int = 0) -> None:
    """Append a titled YAML block to the log file.

    When indent > 0, the entire YAML block (all lines) will be prefixed with the given
    number of spaces to visually nest it under the title.
    """
    write_log(log_file, title)
    y = yaml_to_string(data)
    # Optionally indent every line
    if indent and indent > 0:
        prefix = " " * indent
        y = "".join(prefix + line for line in y.splitlines(True))
    # Ensure consistent line endings and trailing newline
    if not y.endswith("\n"):
        y += "\n"
    write_log(log_file, y, newline=False)

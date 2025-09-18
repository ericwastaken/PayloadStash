from __future__ import annotations

from pathlib import Path
from typing import Optional, Union
import yaml


PathLike = Union[str, Path]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


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

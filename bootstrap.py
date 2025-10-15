#!/usr/bin/env python3
"""
Bootstrap installer for PayloadStash.

Why: On macOS/Homebrew (and some Linux distros), pip is blocked in system-managed
Python per PEP 668. Running `pip install .` may fail with "externally-managed-environment".

Use this script instead. It will:
- Create a local .venv next to this file (if missing).
- Upgrade pip/setuptools/wheel inside it.
- Install this project into the venv (regular or editable mode).
- Optionally run a command inside the venv immediately (via `-- run ...`).

Examples:
- Regular install into .venv:
    python3 bootstrap.py
- Editable (dev) install into .venv:
    python3 bootstrap.py --editable
- Reinstall (force re-install of the package):
    python3 bootstrap.py --reinstall
- Install, then run the CLI (no shell activation needed):
    python3 bootstrap.py -- run payloadstash --help

You can also run the CLI later without activating the venv:
    ./.venv/bin/payloadstash --help
or on Windows PowerShell:
    .\.venv\Scripts\payloadstash.exe --help
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path
import venv

ROOT = Path(__file__).parent.resolve()
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"


def venv_python() -> Path:
    return VENV_DIR / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")


def venv_pip() -> Path:
    return VENV_DIR / ("Scripts" if IS_WINDOWS else "bin") / ("pip.exe" if IS_WINDOWS else "pip")


def ensure_venv():
    if VENV_DIR.exists():
        print(f"[bootstrap] Using existing venv: {VENV_DIR}")
        return
    print(f"[bootstrap] Creating venv at {VENV_DIR} ...")
    builder = venv.EnvBuilder(with_pip=True, clear=False)
    builder.create(str(VENV_DIR))

    # Upgrade packaging tools
    print("[bootstrap] Upgrading pip/setuptools/wheel ...")
    subprocess.check_call([str(venv_pip()), "install", "--upgrade", "pip", "setuptools", "wheel"]) 


def install_project(editable: bool, reinstall: bool):
    args = [str(venv_python()), "-m", "pip", "install"]
    if editable:
        args.append("-e")
    if reinstall:
        args.extend(["--upgrade", "--force-reinstall"])
    args.append(".")
    print("[bootstrap] Installing project:", " ".join(args))
    subprocess.check_call(args, cwd=str(ROOT))


def run_in_venv(cmd: list[str]) -> int:
    # Prepend venv bin path so console scripts are found
    env = os.environ.copy()
    bin_dir = str(VENV_DIR / ("Scripts" if IS_WINDOWS else "bin"))
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    print(f"[bootstrap] Running in venv: {' '.join(cmd)}")
    return subprocess.call(cmd, env=env, cwd=str(ROOT))


def parse_args(argv: list[str]):
    # Split our args from a possible trailing command after `--`
    if "--" in argv:
        idx = argv.index("--")
        ours, tail = argv[:idx], argv[idx + 1 :]
    else:
        ours, tail = argv, []

    p = argparse.ArgumentParser(description="Create local .venv and install this project into it.")
    p.add_argument("--editable", action="store_true", help="Install in editable (-e) mode.")
    p.add_argument("--no-editable", dest="editable", action="store_false", help="Install in regular mode (default).")
    p.add_argument("--reinstall", action="store_true", help="Force reinstall/upgrade of the package.")
    args = p.parse_args(ours)
    return args, tail


def main(argv: list[str]) -> int:
    args, tail = parse_args(argv)
    try:
        ensure_venv()
        install_project(editable=bool(args.editable), reinstall=bool(args.reinstall))
        print("\n[bootstrap] Done. CLI can be run without activating the venv:")
        if IS_WINDOWS:
            print("  .\\.venv\\Scripts\\payloadstash.exe --help")
        else:
            print("  ./payloadstash --help")
        if tail:
            return run_in_venv(tail)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] Error: command failed with exit code {e.returncode}: {e}", file=sys.stderr)
        return e.returncode
    except Exception as e:
        print(f"[bootstrap] Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

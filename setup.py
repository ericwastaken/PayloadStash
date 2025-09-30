#!/usr/bin/env python3
import io
import os
import sys
import subprocess
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.install import install as _install


ROOT = Path(__file__).parent
REQ_FILE = ROOT / "requirements.txt"
VENV_DIR = ROOT / ".venv"


def read_requirements():
    if REQ_FILE.exists():
        with REQ_FILE.open("r", encoding="utf-8") as f:
            reqs = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]
        return reqs
    return []


def read_readme():
    for name in ("README.md", "README.rst", "README.txt"):
        p = ROOT / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return "PayloadStash: YAML‑driven HTTP fetch‑and‑stash for Python."


class install(_install):
    """Custom install that also creates a local venv and installs requirements into it.

    Note: Creating a venv at install time is unconventional, but done here to satisfy the
    project requirement. The venv will be placed at project root as `.venv`.
    """

    def run(self):
        super().run()
        try:
            self._create_venv()
        except Exception as e:
            # Don't fail the package installation just because venv creation failed.
            print(f"[PayloadStash] Warning: Failed to create local .venv: {e}", file=sys.stderr)

    def _create_venv(self):
        import venv

        if VENV_DIR.exists():
            print(f"[PayloadStash] Existing venv found at {VENV_DIR}")
            return
        print(f"[PayloadStash] Creating venv at {VENV_DIR} ...")
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(str(VENV_DIR))

        # Determine python/pip inside the venv
        if os.name == "nt":
            python_bin = VENV_DIR / "Scripts" / "python.exe"
            pip_bin = VENV_DIR / "Scripts" / "pip.exe"
        else:
            python_bin = VENV_DIR / "bin" / "python"
            pip_bin = VENV_DIR / "bin" / "pip"

        # Upgrade pip and install requirements from requirements.txt
        try:
            subprocess.check_call([str(pip_bin), "install", "--upgrade", "pip", "setuptools", "wheel"]) 
            if REQ_FILE.exists():
                print(f"[PayloadStash] Installing requirements from {REQ_FILE} into .venv ...")
                subprocess.check_call([str(pip_bin), "install", "-r", str(REQ_FILE)])
        except subprocess.CalledProcessError as e:
            print(f"[PayloadStash] Warning: pip install inside .venv failed: {e}", file=sys.stderr)


setup(
    name="payloadstash",
    version="1.0.0",
    description="PayloadStash: YAML‑driven HTTP fetch‑and‑stash for Python.",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="",
    packages=find_packages(include=["payload_stash", "payload_stash.*"], exclude=["build*", "dist*", "*.egg-info*"]),
    python_requires=">=3.8",
    install_requires=read_requirements(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "payloadstash=payload_stash.main:main",
        ]
    },
    cmdclass={
        'install': install,
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
### PayloadStash v1.0.0 — Release Notes (2025-09-30)

#### Overview
PayloadStash is a YAML‑driven HTTP fetch‑and‑stash tool for Python. Define your run once, execute a sequence of REST
calls (sequentially or concurrently), and write every response to a clean, predictable folder structure. The engine
resolves YAML anchors/aliases, merges `Defaults` and `Forced` sections, handles failures without stopping the run, and
produces run‑level reports.

#### Highlights
- YAML configuration with anchors/aliases resolution and a persisted `*-resolved.yml` for auditability
- `Defaults` (used only if a request omits a section) and `Forced` (injected into every request, overrides collisions)
- Sequences support sequential or concurrent execution, with `ConcurrencyLimit` on concurrent sequences
- Robust failure handling: individual request failures don’t stop the stash run; statuses/timings are recorded and error
  bodies are written when available
- Content‑Type aware file extensions for saved responses
- Deterministic, timestamped output layout including results CSV and log file
- Secrets injection via a `.env`‑style file with redaction in outputs (`$secrets:<KEY>`)
- First‑class CLI for validate, resolve, and run
- Docker support with helper scripts, including air‑gapped packaging and loading
- Python package distribution and helper script to produce a relocatable zip

Refer to the main repo for more details: https://github.com/ericwastaken/PayloadStash.

#### Installation
- Native (developer install): `python -m pip install -e .` for editable development; reinstall only when dependencies or
  entry point names change.
- Native (package): `pip install .` (project includes a custom `setup.py` step that attempts to create a local `.venv`
  and install requirements there; failure is non‑fatal).
- Docker: use provided build/run/package/load scripts; run writes to host `./output` and resolves relative config paths
  under `./config`.
- Air‑gapped: package on a connected machine, transfer the zip, then run via Docker. See the Docker readme for details.
- Python packaged zip: create with `x-python-package-payloadstash.sh`, transfer `payloadstash-python.zip`, unzip, and install.

#### Requirements
- Python 3.8+
- Docker/Compose for containerized usage (optional)

#### Licensing
- MIT License

#### What’s New in 1.0.0
- First stable release
- Complete YAML specification alignment for config resolution and merging
- Deterministic output layout with results CSV, resolved config, and run log
- Secrets injection and redaction across validation, resolve, and run
- Concurrency controls at the sequence level (`ConcurrencyLimit`)
- Robust error handling that preserves run continuity and artifacts for failed requests
- End‑to‑end Docker workflows, including packaging for air‑gapped environments
- Python packaging and helper zip for offline/relocatable installs

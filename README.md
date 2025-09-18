# PayloadStash – README & YAML Spec

YAML‑driven HTTP fetch‑and‑stash for Python. Define your run once, execute a sequence of REST calls, and write every 
response to a clean, predictable folder structure—**with defaults, forced fields, anchors/aliases, concurrency, 
resilient error handling, and run‑level reporting**.

## Concept

**PayloadStash** reads a YAML config, resolves YAML anchors, merges **Defaults** and **Forced** values into each 
request, and executes requests **sequentially** or **concurrently** according to your **Sequences**. Responses are 
saved to disk with file extensions based on **Content‑Type**.

* **Defaults** – Used **only if** a request does not provide that section.
* **Forced** – Injected into **every** request; **overrides** request and defaults when keys collide.
* **Resolved copy** – After anchor resolution & merges, the effective config is written to `*-resolved.yml` next to 
  the output.
* **Failure handling** – A failing request **does not stop the stash run**. Its HTTP status and timing are recorded,
  output is written (error body if available), and subsequent requests continue.

---

## Quick Start - Native

```bash
# 1) Install (example) - note see DEVELOPER INSTALL below for dev setup!
pip install .

# 2) Run a config
payloadstash run path/to/config.yml --out ./out

# 3) Validate only (no requests)
payloadstash validate path/to/config.yml

# 4) Emit the fully-resolved config (after anchors & merges)
payloadstash resolve path/to/config.yml --out ./out
```

---

## Quick Start - Docker Execution

- Prerequisites: Docker and Docker Compose (v2 preferred).
- Build the image (one-time or when sources change):
  `./x-docker-build-payloadstash.sh`
- Validate a config inside the container (from the host's ./config dir:)
  `./x-docker-run-payloadstash.sh validate config-example.yml`
- Run a config (writes outputs under ./output on the host):
  `./x-docker-run-payloadstash.sh run config-example.yml`

Notes:
- The run script mounts ./config -> /app/config and ./output -> /app/output.
- If you pass --out/-o, it is rewritten to /app/output automatically; otherwise the script adds --out /app/output for 'run'.
- Relative config paths are assumed to be under ./config and are rewritten to /app/config/<path> in the container.
- Before the app starts, the script prints the exact host directories being mounted.

### Exporting to an Air-Gapped server using a Docker Image

- Package all the files (whenever sources or dependencies change) on a host with internet access:
  `sudo ./x-docker-package-payloadstash.sh`
  This will create a ./packaged/payloadstash.zip file.
- Copy the ./packaged/payloadstash.zip file to the air-gapped server.
- On the air-gapped server, extract the package:
  `unzip payloadstash.zip`
  This will create a ./payloadstash/ directory.
- Switch into ./payloadstash then load the image to Docker with: 
  `sudo ./x-docker-load-payloadstash.sh`
- Still from inside this directory, run the cli on the air-gapped server via Docker:
  `x-docker-run-payloadstash.sh run config-example.yml`

---

## Quick Start - Developer Install

If you are developing PayloadStash, you can install it in editable mode with this sequence of commands:

- Do once per environment: `python -m pip install -e .`
- Reinstall only when:
    - dependencies change, or
    - entry point names change.
- Otherwise, edit code and rerun the CLI `payloadstash`, no reinstall needed.

---

## Directory Layout

PayloadStash writes responses to a deterministic path with a **timestamped run folder**:

```
<out>/
  <StashConfig.Name>/
    <RunTimestamp>/
      seqNNN-<Sequence.Name>/
        reqNNN-<RequestKey>-response.<ext>
      <original-config>-results.csv
      <original-config>-resolved.yml
      <original-config>-log.txt
```

**Example**

```
out/
  PXXX-Tester-01/
    2025-09-17T15-42-10Z/
      seq001-GetGeneralData/
        req001-GetConfig-response.json
        req002-GetCatalog-response.json
      seq002-GetPlayer01/
        req001-GetState-response.json
        req002-GrantItem-response.json
      PXXX-Tester-01-results.csv
      PXXX-Tester-01-resolved.yml
      PXXX-Tester-01-log.txt
```

---

## Configuration Overview

A PayloadStash YAML contains two major areas:

1. **Header Groups (Anchors / Aliases)** – optional convenience blocks for DRY configs.
2. **StashConfig** – the actual run definition: name, defaults, forced values, and sequences.

```yml
###########################################################
# Header Groups (Anchors / Aliases)
###########################################################

common_headers: &common_headers
  Content-Type: application/json
  Accept: application/json

common_headers_players: &common_headers_players
  X-App-Client: PayloadStash/1.0
  X-Player-API: v2

###########################################################
# Stash Configuration
###########################################################

StashConfig:
  Name: PXXX-Tester-01

  #########################################################
  # Defaults
  #########################################################
  Defaults:
    URLRoot: https://somehost.com/api/v1
    Headers: *common_headers

  #########################################################
  # Forced Values
  #########################################################
  Forced:
    Headers: {}
    Body:
      someprop: abc
      anotherprop: your value here
    Query: {}

  #########################################################
  # Sequences
  #########################################################
  Sequences:
    - Name: GetGeneralData
      Type: Concurrent
      ConcurrencyLimit: 4
      Requests:
        - GetConfig:
            Method: POST
            URLPath: /getGameConfig
            Headers:
              <<: *common_headers
              X-Request-Scope: config

        - GetCatalog:
            Method: POST
            URLPath: /getGameConfig
            Headers:
              <<: *common_headers
              X-Request-Scope: catalog

    - Name: GetPlayer01
      Type: Sequential
      Requests:
        - GetState:
            Method: POST
            URLPath: /getState
            Headers:
              <<: [*common_headers, *common_headers_players]
              X-Request-Scope: state

        - GrantItem:
            Method: POST
            URLPath: /grantItem
            Headers:
              <<: [*common_headers, *common_headers_players]
              X-Request-Scope: grant
```

---

## Full YAML Schema (informal)

```yml
# 0) Optional header groups for anchors/aliases
<alias_name>: &<alias_name>
  <HeaderKey>: <string>
  ...repeat as needed...

Dynamics:
  patterns:
    userid_hex_prefixed:
      template: "1234${hex:20}"
    userid_hex_structured:
      template: "1234${hex:22}${choice:teams}${hex:4}${hex:2}00"
    userid_uuid_v4:
      template: "${uuidv4}"

  sets:
    teams: ["0","1","2","3"]

StashConfig:
  Name: <string>

  Defaults:
    # Required Defaults
    URLRoot: <string>
    FlowControl:
      # Number of seconds in between sequences and requests (default: 0)
      DelaySeconds: <int>
      TimeoutSeconds: <int>
      
    # Optional Defaults
    Headers?: { <k>: <v>, ... }
    Body?:    { <k>: <v>, ... }
    # Example: compute a timestamp at resolve-time
    # Body.timestamp can call the built-in timestamp() helper:
    #   timestamp: { $func: timestamp, format: iso_8601 }
    Query?:   { <k>: <v>, ... }

  Forced?:
    Headers?: { <k>: <v>, ... }
    Body?:    { <k>: <v>, ... }
    Query?:   { <k>: <v>, ... }
  
  # Optional global retry policy (applies when a request omits Retry)
  Retry?:
    Attempts: <int>                 # total tries including the first (e.g., 3)
    BackoffStrategy: <fixed|exponential>
    BackoffSeconds: <number>        # base delay (e.g., 0.5)
    Multiplier?: <number>           # exponential growth factor (e.g., 2.0)
    MaxBackoffSeconds?: <number>    # cap per-try backoff
    MaxElapsedSeconds?: <number>    # overall cap across all retries (optional)
    Jitter?: <bool>                 # true = add full jitter (random 0..backoff), false = no jitter
    RetryOnStatus?: [<int>, ...]    # HTTP codes to retry (e.g., [429, 500, 502, 503, 504])
    RetryOnNetworkErrors?: <bool>   # retry on DNS/connect/reset/timeouts (default: true)
    RetryOnTimeouts?: <bool>        # retry when client timeout occurs (default: true)

  Sequences:
    - Name: <string>
      Type: <Sequential|Concurrent>
      ConcurrencyLimit?: <int>
      Requests:
        - <RequestKey>:
            Method: <GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS>
            URLPath: <string>
            Headers?: { <k>: <v>, ... }
            Body?:    { <k>: <v>, ... }
            Query?:   { <k>: <v>, ... }
            FlowControl?:
              DelaySeconds?: <int>
              TimeoutSeconds?: <int>
            # Optional per-request retry policy (overrides Defaults.Retry if present)
            Retry?:
              Attempts: <int>
              BackoffStrategy: <fixed|exponential>
              BackoffSeconds: <number>
              Multiplier?: <number>
              MaxBackoffSeconds?: <number>
              MaxElapsedSeconds?: <number>
              Jitter?: <none|full|equal>
              RetryOnStatus?: [<int>, ...]
              RetryOnNetworkErrors?: <bool>
              RetryOnTimeouts?: <bool>
```

### Functions & Dynamics inside configs

You can compute certain values using a special object syntax. The following helpers are available:

Functions:
- timestamp: returns the current UTC time in one of several formats.

Usage forms:
- `{ $func: timestamp, format: iso_8601 }`
- With control over when it is evaluated:
  - `{ $func: timestamp, format: iso_8601, when: request }`

Supported formats for timestamp: epoch_ms, epoch_s, iso_8601.

When parameter:
- when: resolve (default) – evaluate during config resolution (e.g., when writing *-resolved.yml).
- when: request – defer evaluation until the moment you are about to send the request.

How deferral works:
- During config resolution, request-time functions are preserved as a marker like:
  `{"$deferred": {"func": "timestamp", "format": "epoch_ms"}}`
- At send-time, call the helper to resolve these markers in the object you are about to send:

```python
from payload_stash.config_utility import resolve_deferred

ready_headers = resolve_deferred(headers)
ready_query = resolve_deferred(query)
ready_body = resolve_deferred(body)
```

Example adding timestamps with both timings:

```yml
StashConfig:
  Name: WithTimestamp
  Defaults:
    Body:
      ts_resolve: { $func: timestamp, format: iso_8601 }
      ts_request: { $func: timestamp, format: epoch_ms, when: request }
  Sequences:
    - Name: OnlySeq
      Type: Sequential
      Requests:
        - Ping:
            Method: GET
            URLPath: /health
            Body:
              now_req: { $func: timestamp, format: iso_8601, when: request }
```

Dynamics:
- Dynamics let you declare reusable ID or token patterns once and then materialize them anywhere in Headers, Query, or 
Body using a special object form: `{ $dynamic: <patternName>, ... }`.
- Unlike functions (which call code), dynamics expand a named template you define under the top-level dynamics: section 
of your YAML.

Where you declare them:
- Top-level section (sibling of StashConfig):

  ```yml
  dynamics:
    patterns:
      user_structured:
        template: "1234${hex:22}${choice:teams}00"
      user_uuid:
        template: "user-${uuidv4}"
    sets:
      teams: ["00", "01", "02", "03"]
  ```
- patterns: A map of pattern names to a template string.
- sets: Named lists used by `${choice:<setName>}` placeholders inside templates.

Template placeholders supported:
- `${hex:N}` — N random hexadecimal characters, uppercase A–F guaranteed.
- `${alphanumeric:N}` — N random characters from 0-9, A-Z, a-z.
- `${numeric:N}` — N random digits 0-9.
- `${alpha:N}` — N random letters A-Z, a-z.
- `${uuidv4}` — A standard UUID v4 string, e.g., 3f2b0b9a-3c03-4b0a-b4ad-5d9d3f6e45a7.
- `${choice:setName}` — Pick one random element from a named set, e.g., teams above returns one of ["00", "01", "02", "03"].
- `${timestamp[:format]}` — Current UTC timestamp; format options: iso_8601 (default), epoch_ms, epoch_s.

Using a dynamic in a request:
- Resolve-time (default): materialize immediately during config resolution.

  ```yml
  Body:
    userId: { $dynamic: user_structured }
  ```
  
- Request-time deferral: keep as a marker until the HTTP call is about to be sent, so every request gets a fresh value.

  ```yml
  Body:
    userId: { $dynamic: user_structured, when: request }
  ```

When parameter for dynamics:
- when: resolve (default) — expand the template while creating the *-resolved.yml file. The resulting literal string 
  appears in that file.
- when: request — store a deferred marker in the resolved file; the CLI will expand it right before sending the request 
  so each attempt (or each request in a loop) can get a unique value.

Notes and behavior:
- Scope: dynamics is top-level and applies to the entire file. Pattern names must be unique. You can keep multiple 
  pattern families in one file by namespacing, e.g., player_uuid_v4.
- Determinism: expansions are random by design (hex/choice). Use resolve-time if you want to audit exact values in 
  *-resolved.yml; use request-time to get per-request variety.
- Coexistence with Functions: you can freely mix $func and $dynamic in the same object. Both support when with the same 
  semantics.
- Resolved output: request-time dynamics are preserved in *-resolved.yml as a generic $deferred marker and expanded by 
  the runner at send-time (similar to $func deferral).

End-to-end example:

  ```yml
  dynamics:
    patterns:
      player_id:
        template: "p-${hex:8}-${choice:teams}-${hex:4}"
    sets:
      teams: ["NORTH", "SOUTH", "EAST", "WEST"]

  StashConfig:
    Name: WithDynamics
    Defaults:
      Body:
        # resolve-time value: appears literal in *-resolved.yml
        example_id_resolve: { $dynamic: player_id }
        # request-time: shows as deferred in *-resolved.yml and is generated at send-time
        example_id_request: { $dynamic: player_id, when: request }
    Sequences:
      - Name: OnlySeq
        Type: Sequential
        Requests:
          - Ping:
              Method: GET
              URLPath: /health
              Body:
                per_call_id: { $dynamic: player_id, when: request }
  ```
---

## Merge & Precedence Rules

PayloadStash computes each request’s **effective** sections in this order:

1. Start with empty `{Headers, Body, Query}`.
2. If the request defines a section, copy it in.
3. If the request omits a section, copy from **Defaults**.
4. **Forced** is merged last and overrides.
5. `URLRoot` comes from Defaults only. It is not allowed inside a Request.

Example: If `Defaults.Body.team = "blue"`, `Request.Body.team` omitted, and `Forced.Body.team = "green"`, 
then `team == "green"`.

---

## Anchors, Aliases & Header Merging

YAML anchors are resolved before merging Defaults/Forced.

```yml
common_headers: &common_headers
  Content-Type: application/json
  Accept: application/json

player_headers: &player_headers
  X-App-Client: PayloadStash/1.0
  X-Player-API: v2

Headers:
  <<: [*common_headers, *player_headers]
  X-Request-Scope: state
```

If the same key appears in multiple merged maps, the last one wins. After anchor resolution, PayloadStash writes 
`*-resolved.yml` so you can audit.

---

## Sequences & Concurrency

* `Sequences` are executed **in the order listed**.
* Each sequence has a `Type`:
    * **Sequential**: requests execute one-at-a-time.
    * **Concurrent**: requests execute in parallel (async/await). `ConcurrencyLimit` caps fan-out.
* A failed request does not stop the run. Its response, HTTP status, and timing are written; execution continues.

## Flow Control

Control pacing and client timeouts via a FlowControl block.

Location:
- Required at Defaults: Defaults.FlowControl with both fields present.
- Optional per-request override at Request.FlowControl (either field may be provided to override that aspect for the request).

Fields:
- DelaySeconds: Non-negative integer. Delay applied between requests and when advancing to the next sequence.
- TimeoutSeconds: Non-negative integer. Client-side request timeout.

Example (Defaults and per-request override):

```yml
StashConfig:
  Name: WithDelayAndTimeout
  Defaults:
    URLRoot: https://api.example.com
    FlowControl:
      DelaySeconds: 1
      TimeoutSeconds: 5
  Sequences:
    - Name: A
      Type: Sequential
      Requests:
        - First:
            Method: GET
            URLPath: /a
        - Second:
            Method: GET
            URLPath: /b
            FlowControl:
              TimeoutSeconds: 1   # override only timeout for this request
              # DelaySeconds omitted -> uses Defaults.FlowControl.DelaySeconds
    - Name: B
      Type: Concurrent
      ConcurrencyLimit: 3
      Requests:
        - One:
            Method: GET
            URLPath: /x
        - Two:
            Method: GET
            URLPath: /y
```

---

## Retry Explained

The `Retry` block defines how PayloadStash retries failed HTTP requests.

### Location

* Can be defined under `Defaults` to apply globally.
* Can be overridden or disabled (`Retry: null`) at the per-request level.

### Fields

* **Attempts** – total tries including the first.
  `Attempts: 3` = first try + up to 2 retries.
* **BackoffStrategy** – either `fixed` or `exponential`.
    * `fixed`: each retry waits the same `BackoffSeconds`.
    * `exponential`: waits grow by a `Multiplier` each retry (e.g., 0.5s, 1s, 2s, 4s…).
* **BackoffSeconds** – base wait time before applying strategy.
* **Multiplier** – growth factor for exponential backoff.
* **MaxBackoffSeconds** – maximum wait allowed for a single retry.
* **MaxElapsedSeconds** – maximum total time spent across all retries.
* **Jitter** – `true` adds **full jitter** (random delay between 0 and backoff). `false` means no jitter.
* **RetryOnStatus** – list of HTTP status codes to retry (e.g., 429, 500, 502, 503, 504).
* **RetryOnNetworkErrors** – retry on DNS/connect/reset errors (default: true).
* **RetryOnTimeouts** – retry when client timeout occurs (default: true).

### Disabling Retry

* **Globally**: set `Defaults.Retry: null` or omit it entirely.
* **Per request**: set `Retry: null` under that request.

### Example

```yml
Defaults:
  Retry:
    Attempts: 4
    BackoffStrategy: exponential
    BackoffSeconds: 0.5
    Multiplier: 2.0
    MaxBackoffSeconds: 10
    Jitter: true
    RetryOnStatus: [429, 500, 502, 503, 504]

Sequences:
  - Name: ExampleSeq
    Type: Sequential
    Requests:
      - GetState:
          Method: GET
          URLPath: /state
          Retry: null   # disable retry here
      - GetConfig:
          Method: GET
          URLPath: /config
          # inherits Defaults.Retry with jitter enabled
```

---

## Output Files & Extensions

Each request writes one file per request, named as `reqNNN-<RequestKey>-response.<ext>`, where NNN is the 1-based index within its sequence. The extension is derived from the response Content‑Type.

| Content-Type                | Extension |
| --------------------------- | --------- |
| application/json            | .json     |
| text/plain                  | .txt      |
| text/csv                    | .csv      |
| application/xml or text/xml | .xml      |
| application/pdf             | .pdf      |
| image/\*                    | .png/.jpg |
| unknown/missing             | .txt      |

**Path construction**

```
<out>/<StashConfig.Name>/<RunTimestamp>/seqNNN-<Sequence.Name>/reqNNN-<RequestKey>-response.<ext>
```

---

## Run Results CSV

Each run produces a `<original-config>-results.csv` file in the run’s timestamped directory. This file logs metadata 
for every request executed.

**File path:**

```
<out>/<StashConfig.Name>/<RunTimestamp>/<original-config>-results.csv
```

**Columns:**

* `sequence` – the sequence name.
* `request` – the request key.
* `timestamp` – UTC timestamp when executed.
* `status` – HTTP status code (or -1 if none).
* `duration_ms` – request time in ms.
* `attempts` – number of attempts made.

**Example:**

```csv
sequence,request,timestamp,status,duration_ms,attempts
seq001-GetGeneralData,req001-GetConfig,2025-09-17T15:42:11Z,200,123,1
seq001-GetGeneralData,req002-GetCatalog,2025-09-17T15:42:11Z,500,87,1
seq002-GetPlayer01,req001-GetState,2025-09-17T15:42:12Z,200,212,1
seq002-GetPlayer01,req002-GrantItem,2025-09-17T15:42:13Z,200,145,1
```

---

## Run Log

Every run produces a detailed human-readable log file to aid observability and troubleshooting.

- File name: <original-config>-log.txt
- Location: alongside the run’s resolved config and results CSV in the timestamped run directory
- Created by: payloadstash run
- Purpose: records high-detail, chronological information about the run, including start/end markers, configuration 
  resolution notices, per-request progress markers, retry decisions, HTTP status summaries, and any non-fatal errors 
  encountered. This log is intended to complement the structured <original-config>-results.csv file.

File path:

```
<out>/<StashConfig.Name>/<RunTimestamp>/<original-config>-log.txt
```

Example:

```
out/PXXX-Tester-01/2025-09-17T15-42-10Z/PXXX-Tester-01-log.txt
```

---

## CLI Usage

```bash
payloadstash run CONFIG.yml --out ./out [--dry-run] [--yes]

payloadstash validate CONFIG.yml

payloadstash resolve CONFIG.yml --out ./out
```

Flags:
- --dry-run: Resolve and log actions without making HTTP requests.
- --yes: Automatically continue without the interactive "Continue? [y/N]" prompt.

Exit codes:

* 0 = run success, no validation errors and all requests were http 200s.
* 1 = run success, but at least one http request was other than http 200s.
* 9 = run not successful due to a validation error, or output write error. Output might be partial.

> **Note:** Individual request errors will not cause a premature exit.

---

## Validation Rules

* `StashConfig.Name` required.
* `StashConfig.Defaults.URLRoot` required.
* `StashConfig.Defaults.FlowControl` required (must include DelaySeconds and TimeoutSeconds).
* At least one sequence.
* Each sequence must have Name, Type, and at least one Request.
* Each request must have one key, Method, and URLPath.
* URLRoot is not allowed inside a Request.
* Headers, Body, Query must be maps.
* ConcurrencyLimit is only allowed for Type=Concurrent and must be >0 if present.

---

## Examples

### Minimal

```yml
StashConfig:
  Name: MiniRun
  Defaults:
    URLRoot: https://api.example.com
  Sequences:
    - Name: OnlySeq
      Type: Sequential
      Requests:
        - Ping:
            Method: GET
            URLPath: /health
```

### With Defaults & Forced

```yml
common: &common
  Accept: application/json

StashConfig:
  Name: WithDefaultsForced
  Defaults:
    URLRoot: https://api.example.com/v1
    Headers:
      <<: *common
      User-Agent: PayloadStash/1.0
  Forced:
    Headers:
      X-Env: prod
    Query:
      lang: en-US
  Sequences:
    - Name: SeqA
      Type: Concurrent
      ConcurrencyLimit: 3
      Requests:
        - A:
            Method: GET
            URLPath: /a
        - B:
            Method: GET
            URLPath: /b
            Headers:
              Authorization: Bearer TOKEN
```

---

## Implementation Notes

* Async runtime: asyncio with httpx/aiohttp.
* Anchor resolution: resolve << merges, write \*-resolved.yml inside timestamp folder.
* URL concat: `URLRoot.rstrip('/') + '/' + URLPath.lstrip('/')`.
* Error handling: record status/body; do not abort run; log in <original-config>-results.csv.
* Case handling: headers case-insensitive.
* Timing: capture duration\_ms and timestamp per request.
* Extensibility: TimeoutSeconds and Retry possible.

---

### FAQ

* Failed requests are recorded, not fatal.
* Resolved config written inside timestamped folder.

---

Happy stashing!!️


from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone
import click
import yaml

from . import __version__
from .config_schema import validate_config_path, format_validation_error, build_resolved_config_dict
from .config_utility import evaluate_expect, resolve_response_path


def _write_markdown_report(report_path, sc_name: str, config_stem: str, started_ts: str, entries: list) -> None:
    # New function. Generates a human-readable markdown report of the run, inspired by
    # the examen test runner's output format. Entries are accumulated by _build_report_entry
    # inside _process_single_request and sorted into config order at write time.
    # Requests with Expect contribute to the pass/fail summary; requests without Expect
    # are listed as "Executed" and excluded from pass/fail counts.
    import json as _json

    entries_sorted = sorted(entries, key=lambda e: e["sort_key"])
    total = len(entries_sorted)

    # Tally pass/fail/executed (only requests with Expect count toward pass/fail)
    n_passed = sum(1 for e in entries_sorted if e["expect_results"] and all(r[1] for r in e["expect_results"]))
    n_failed = sum(1 for e in entries_sorted if e["expect_results"] and any(not r[1] for r in e["expect_results"]))
    n_executed = total - n_passed - n_failed  # no Expect or error

    lines = []
    lines.append(f"# PayloadStash — {sc_name}\n")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| **Config** | `{config_stem}.yml` |")
    lines.append(f"| **Started** | {started_ts} |")
    lines.append("")

    lines.append("## Summary\n")
    lines.append("| Status | Count |")
    lines.append("|---|---|")
    if n_passed or n_failed:
        lines.append(f"| ✅ Passed | {n_passed} |")
        lines.append(f"| ❌ Failed | {n_failed} |")
    if n_executed:
        lines.append(f"| 📦 Executed | {n_executed} |")
    lines.append(f"| **Total** | **{total}** |")
    lines.append("")

    # Assertion list — one row per assertion across all requests that have Expect.
    # Requests without Expect are omitted here (they appear as 📦 in the detail sections).
    expect_entries = [e for e in entries_sorted if e["expect_results"]]
    if expect_entries:
        lines.append("## Assertions\n")
        lines.append("| Request | Assertion | |")
        lines.append("|---|---|---|")
        for e in expect_entries:
            for label, passed, _ in e["expect_results"]:
                icon = "✅" if passed else "❌"
                lines.append(f"| `{e['r_key']}` | `{label}` | {icon} |")
        lines.append("")

    lines.append("---\n")

    def _body_snippet(text: str, ct: str | None) -> str:
        limit = 8192
        truncated = len(text) > limit
        snip = text[:limit]
        lang = "json"
        if ct and "xml" in ct:
            lang = "xml"
        elif ct and "text" in ct:
            lang = "text"
        result = f"```{lang}\n{snip}\n```"
        if truncated:
            result += f"\n*… ({len(text) - limit} more bytes)*"
        return result

    for global_idx, entry in enumerate(entries_sorted, start=1):
        r_key = entry["r_key"]
        method = entry["method"]
        full_url = entry["full_url"]
        status = entry["status"]
        duration_ms = entry["duration_ms"]
        headers_out = entry["headers_out"] or {}
        body_res = entry["body_res"]
        resp_text = entry["resp_text"] or ""
        ct_value = entry["ct_value"]
        capture_cfg = entry["capture_cfg"]
        captured_values = entry["captured_values"]
        expect_results = entry["expect_results"]

        # Determine status badge
        if expect_results is not None:
            if all(r[1] for r in expect_results):
                badge = "✅ PASS"
            else:
                badge = "❌ FAIL"
        else:
            badge = f"📦 {status}" if status != -1 else "❌ ERROR"

        lines.append(f"## [{global_idx}/{total}] {r_key}\n")
        lines.append(f"**Status:** {badge}\n")
        lines.append("### Request\n")

        # Request block: METHOD URL + notable headers
        req_header_lines = [f"{method} {full_url}"]
        for hk, hv in headers_out.items():
            if hk.lower() not in ("content-type", "content-length"):
                req_header_lines.append(f"{hk}: {hv}")
        lines.append("```")
        lines.extend(req_header_lines)
        lines.append("```\n")

        if body_res is not None:
            try:
                body_str = _json.dumps(body_res, indent=2, ensure_ascii=False)
            except Exception:
                body_str = str(body_res)
            lines.append("**Body:**\n")
            lines.append(_body_snippet(body_str, "application/json"))
            lines.append("")

        lines.append("### Response\n")
        status_label = str(status) if status != -1 else "ERROR"
        lines.append(f"**Status:** {status_label}  **Duration:** {duration_ms}ms\n")
        if resp_text:
            lines.append(_body_snippet(resp_text, ct_value))
            lines.append("")

        if capture_cfg and captured_values:
            lines.append("### Captured Values\n")
            for cap_name, cap_path in capture_cfg.items():
                val = captured_values.get(cap_name)
                lines.append(f"- `{cap_name}` ← `{cap_path}` = `{val!r}`")
            lines.append("")

        if expect_results:
            lines.append("### Assertions\n")
            for label, passed, detail in expect_results:
                mark = "✅" if passed else "❌"
                lines.append(f"- {mark} {label}")
                if detail:
                    lines.append(f"  > actual: `{detail.strip()}`")
            lines.append("")

        lines.append("---\n")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


@click.group(help="PayloadStash CLI")
@click.version_option(__version__, prog_name="PayloadStash")
def main():
    """PayloadStash top-level command group."""
    pass


@main.command()
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--writeResolved", is_flag=True, help="Apply anchors, Defaults and Forced into each request and write <file>-resolved.yml next to CONFIG.")
@click.option("--secrets", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Path to secrets file (KEY=VALUE lines) to resolve $secrets references.")
def validate(config: Path, writeresolved: bool, secrets: Path | None):
    """Validate a YAML CONFIG file against the PayloadStash schema.

    When --writeResolved is provided, writes a fully-resolved copy named
    '<original-stem>-resolved.yml' in the same directory as the CONFIG file.
    """
    try:
        cfg = validate_config_path(config)
        # Load secrets if provided
        secrets_map = None
        if secrets is not None:
            try:
                from .config_utility import load_secrets_file
                secrets_map = load_secrets_file(secrets)
            except Exception as se:
                click.echo(f"Failed to load secrets file: {se}", err=True)
                sys.exit(1)
        # Attempt to resolve with actual secrets (but do not write yet). This will fail if secrets are required but missing/unknown.
        _ = build_resolved_config_dict(cfg, secrets=secrets_map, redact_secrets=False)

        # If we reach here, validation passed
        sc_name = cfg.StashConfig.Name
        sequences = len(cfg.StashConfig.Sequences)
        click.echo(f"OK: {config} is a valid PayloadStash config. Name='{sc_name}', Sequences={sequences}")

        if writeresolved:
            resolved_redacted = build_resolved_config_dict(cfg, secrets=secrets_map, redact_secrets=True)

            class NoAliasDumper(yaml.SafeDumper):
                def ignore_aliases(self, data):
                    return True

            out_path = config.with_name(f"{config.stem}-resolved.yml")
            try:
                with out_path.open('w', encoding='utf-8') as f:
                    yaml.dump(resolved_redacted, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
                click.echo(f"Wrote resolved config: {out_path}")
            except Exception as we:
                click.echo(f"Failed to write resolved config: {we}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(format_validation_error(e), err=True)
        sys.exit(1)


@main.command(help="Run a PayloadStash config: validate, resolve, write resolved, then process sequences and requests.")
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path), help="Output directory root for run artifacts.")
@click.option("--dry-run", is_flag=True, help="Resolve request configs and log actions, but do not actually make HTTP requests.")
@click.option("--yes", is_flag=True, help="Automatically continue without prompting for confirmation.")
@click.option("--secrets", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Path to secrets file (KEY=VALUE lines) to resolve $secrets references.")

def run(config: Path, out_dir: Path, dry_run: bool, yes: bool, secrets: Path | None):
    # 1) Basic argument validation
    if out_dir is None:
        click.echo("Error: --out is required", err=True)
        sys.exit(9)

    # 2) Validate config and build resolved dicts (resolve-time expansion)
    try:
        cfg = validate_config_path(config)
        # Load secrets
        secrets_map = None
        if secrets is not None:
            try:
                from .config_utility import load_secrets_file
                secrets_map = load_secrets_file(secrets)
            except Exception as se:
                click.echo(f"Failed to load secrets file: {se}", err=True)
                sys.exit(9)
        # Build actual and redacted resolved dicts
        resolved_actual = build_resolved_config_dict(cfg, secrets=secrets_map, redact_secrets=False)
        resolved_redacted = build_resolved_config_dict(cfg, secrets=secrets_map, redact_secrets=True)
    except Exception as e:
        click.echo(format_validation_error(e), err=True)
        sys.exit(9)

    # 3) Determine run folder
    sc_name = cfg.StashConfig.Name
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_root = out_dir / sc_name / ts

    # 4) Create directories and write resolved config into run folder
    try:
        run_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        click.echo(f"Error: failed to create output directory '{run_root}': {e}", err=True)
        sys.exit(9)

    class NoAliasDumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    resolved_path = run_root / f"{config.stem}-resolved.yml"
    try:
        with resolved_path.open('w', encoding='utf-8') as f:
            yaml.dump(resolved_redacted, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
    except Exception as e:
        click.echo(f"Error: failed to write resolved config: {e}", err=True)
        sys.exit(9)

    # Prepare log file path
    log_path = run_root / f"{config.stem}-run.log"

    # Prepare results CSV path
    results_csv_path = run_root / f"{config.stem}-results.csv"

    # 5) Print summary of what the run config will do and the output location
    sequences = cfg.StashConfig.Sequences
    total_requests = sum(len(s.Requests) for s in sequences)
    click.echo("PayloadStash run summary:")
    click.echo(f"  Name:            {sc_name}")
    click.echo(f"  Sequences:       {len(sequences)}")
    click.echo(f"  Total Requests:  {total_requests}")
    click.echo(f"  Output folder:   {run_root}")
    click.echo(f"  Resolved config: {resolved_path}")
    click.echo(f"  Log file:        {log_path}")
    if dry_run:
        click.echo("  Mode:            DRY-RUN (no HTTP calls)")

    # 6) User confirmation prompt
    try:
        if yes:
            click.echo("Auto-continue (--yes supplied).")
            resp = "yes"
        else:
            click.echo(" Continue? [y/N]: ", nl=False)
            resp = click.get_text_stream('stdin').readline().strip().lower()
        if resp in ("y", "yes"):
            click.echo(f"\nProcessing {sc_name}")

            from .utility import start_run_log, write_log, log_yaml, write_yaml_file
            from .config_utility import resolve_deferred
            from .request_manager import RequestManager
            import time
            from urllib import parse as urlparse
            import json
            # Size the connection pool conservatively; concurrency is determined by config
            pool_size = 50
            rm = RequestManager(pool_maxsize=pool_size)

            start_run_log(log_path, ts, sc_name, resolved_path)

            # Logging helpers with secret redaction
            def _redact_text(s: str) -> str:
                if not secrets_map or not isinstance(s, str):
                    return s
                out = s
                try:
                    # Replace longer secrets first to avoid partial overlaps causing leakage
                    for _k, _v in sorted(secrets_map.items(), key=lambda kv: len(str(kv[1] or "")), reverse=True):
                        if _v:
                            out = out.replace(str(_v), "***REDACTED***")
                except Exception:
                    pass
                return out

            def _log_redacted(message: str) -> None:
                try:
                    write_log(log_path, _redact_text(message))
                except Exception:
                    write_log(log_path, message)

            # Initialize results CSV with header.
            # Added expect_passed and expect_failed columns to track Expect assertion results.
            # Existing columns are unchanged; new columns append to the right so old parsers
            # that read by position are unaffected.
            try:
                import csv
                with results_csv_path.open('w', encoding='utf-8', newline='') as cf:
                    w = csv.writer(cf)
                    w.writerow(["sequence", "request", "timestamp", "status", "duration_ms", "attempts", "expect_passed", "expect_failed"])
            except Exception as e:
                _log_redacted(f"Warning: failed to initialize results CSV '{results_csv_path}': {e}")

            # Run-level state added for Capture and Expect features.
            # - captured: accumulates values extracted from responses via Capture blocks.
            #   Later requests reference these via { $pattern: "${captured:KEY}" } in any field.
            # - captures_lock: guards captured for thread-safe reads/writes in concurrent sequences.
            #   Also reused to guard run_expect_failures since it's mutated from request threads.
            # - report_entries: collects per-request data for the markdown report written at run end.
            # - run_expect_failures: mutable list used as a counter so the closure can increment it.
            from threading import Lock as _Lock
            captured: dict = {}
            captures_lock = _Lock()
            report_entries: list = []
            report_lock = _Lock()
            run_expect_failures: list = [0]

            # Pull defaults (including URLRoot) and flow control
            sc_resolved = resolved_actual.get("StashConfig", {})
            defaults_resolved = sc_resolved.get("Defaults", {})
            url_root: str = defaults_resolved.get("URLRoot") or ""
            flow_cfg_defaults = (defaults_resolved.get("FlowControl") or {})
            default_delay = flow_cfg_defaults.get("DelaySeconds")
            default_timeout = flow_cfg_defaults.get("TimeoutSeconds")
            # set a safe default pacing when unspecified
            if default_delay is None:
                default_delay = 0

            seq_dicts = sc_resolved.get("Sequences", [])
            total_seq = len(seq_dicts)
            from threading import Lock
            csv_lock = Lock()
            import csv as _csv

            # Helper to redact any occurrences of secret values in strings within a nested structure
            def _redact_struct(obj):
                if not secrets_map:
                    return obj
                def repl_str(s: str) -> str:
                    out = s
                    try:
                        for _k, _v in secrets_map.items():
                            if _v:
                                out = out.replace(str(_v), "***REDACTED***")
                    except Exception:
                        pass
                    return out
                if isinstance(obj, dict):
                    return {k: _redact_struct(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_redact_struct(v) for v in obj]
                if isinstance(obj, str):
                    return repl_str(obj)
                return obj


            def _append_result_row(seq_name: str, req_name: str, ts_iso: str, status_code: int, duration_ms: int, attempts: int, expect_passed: int = 0, expect_failed: int = 0) -> None:
                try:
                    with csv_lock:
                        with results_csv_path.open('a', encoding='utf-8', newline='') as cf:
                            w = _csv.writer(cf)
                            w.writerow([seq_name, req_name, ts_iso, status_code, duration_ms, attempts, expect_passed, expect_failed])
                except Exception as e:
                    _log_redacted(f"Warning: failed to append to results CSV: {e}")

            for i, seq_d in enumerate(seq_dicts, start=1):
                s_name = seq_d.get("Name")
                s_type = seq_d.get("Type")
                s_conc = seq_d.get("ConcurrencyLimit")
                msg = f"Processing sequence {i}/{total_seq}: {s_name} (Type={s_type}"
                if s_conc is not None:
                    msg += f", ConcurrencyLimit={s_conc}"
                msg += ")"
                click.echo(msg)
                _log_redacted(msg)

                # Create per-sequence output directory (seqNNN-Name)
                seq_dir_name = f"seq{i:03d}-{s_name}"
                seq_out_dir = run_root / seq_dir_name
                try:
                    seq_out_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    _log_redacted(f"  Warning: failed to create sequence directory '{seq_out_dir}': {e}")

                # Prepare all requests for this sequence.
                # Previously, this loop also resolved $deferred values (request-time dynamics) and
                # built the final URL/headers/body for each request. That resolution has been moved
                # into _process_single_request so it runs just before each HTTP call.
                #
                # Why the move: the new Capture feature stores values from one response and makes
                # them available to later requests via { $pattern: "${captured:KEY}" }. Those values
                # don't exist until a request has actually run, so they can't be resolved upfront for
                # all requests at once. By resolving everything just-in-time inside _process_single_request,
                # $pattern and other $deferred markers all resolve in a single pass with
                # the correct runtime state. Existing behavior for all non-Capture configs is
                # identical — deferred values still resolve at the same logical moment.
                req_items = seq_d.get("Requests", [])
                prepared_requests = []
                insecure_defaults = bool((defaults_resolved or {}).get("InsecureTLS") or False)
                for j, req_item in enumerate(req_items, start=1):
                    if not isinstance(req_item, dict) or len(req_item) != 1:
                        _log_redacted(f"  Skipping malformed request at index {j}")
                        continue
                    r_key, r_val = next(iter(req_item.items()))
                    r_flow = r_val.get("FlowControl") or {}
                    timeout_s = r_flow.get("TimeoutSeconds", default_timeout)
                    delay_seconds = r_flow.get("DelaySeconds", default_delay)
                    effective_retry = r_val.get("Retry") if isinstance(r_val, dict) else None
                    response_opts = None
                    try:
                        ro = r_val.get("Response") if isinstance(r_val, dict) else None
                        if isinstance(ro, dict):
                            response_opts = {k: v for k, v in ro.items() if k in ("PrettyPrint", "Sort")}
                    except Exception:
                        response_opts = None
                    insecure_eff = insecure_defaults
                    try:
                        if isinstance(r_val, dict) and "InsecureTLS" in r_val:
                            insecure_eff = bool(r_val.get("InsecureTLS"))
                    except Exception:
                        pass
                    prepared_requests.append((j, r_key, r_val, timeout_s, delay_seconds, effective_retry, response_opts, bool(insecure_eff)))

                # _maybe_format_response is unchanged from the original; extracted here to avoid
                # redefining it inside _process_single_request on every call.
                from .utility import yaml_to_string
                import json as _json

                def _maybe_format_response(text_in: str, content_type: str | None, resp_cfg: dict | None) -> str:
                    try:
                        if not isinstance(resp_cfg, dict) or not resp_cfg:
                            return text_in
                        sort_flag = bool(resp_cfg.get("Sort"))
                        pretty_flag = bool(resp_cfg.get("PrettyPrint")) or sort_flag
                        if not pretty_flag:
                            return text_in
                        ct_main = None
                        if isinstance(content_type, str) and content_type:
                            ct_main = content_type.split(';', 1)[0].strip().lower()
                        if ct_main and (ct_main.endswith('/json') or ct_main == 'application/json'):
                            try:
                                from rich.console import Console
                                from rich.json import JSON as RichJSON
                                import io as _io
                                s = _io.StringIO()
                                console = Console(file=s, no_color=True, force_jupyter=False, force_terminal=False, color_system=None, width=120)
                                console.print(RichJSON(text_in, indent=2, sort_keys=sort_flag))
                                return s.getvalue().rstrip() + "\n"
                            except Exception:
                                import json as _j2
                                try:
                                    return _j2.dumps(_j2.loads(text_in), indent=2, sort_keys=sort_flag, ensure_ascii=False) + "\n"
                                except Exception:
                                    return text_in
                        if ct_main and (ct_main in ('application/xml', 'text/xml') or ct_main.endswith('+xml')):
                            try:
                                from xml.dom import minidom as _minidom
                                dom = _minidom.parseString(text_in.encode('utf-8'))
                                if sort_flag:
                                    def sort_node(node):
                                        try:
                                            if node.nodeType == node.ELEMENT_NODE:
                                                if node.hasAttributes():
                                                    attrs = node.attributes
                                                    names = sorted([attrs.item(ii).name for ii in range(attrs.length)])
                                                    for n in names:
                                                        v = attrs.get(n).value
                                                        attrs.removeNamedItem(n)
                                                        attrs.setNamedItem(node.ownerDocument.createAttribute(n))
                                                        attrs.get(n).value = v
                                                for c in list(node.childNodes):
                                                    sort_node(c)
                                                elems = [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE]
                                                others = [c for c in node.childNodes if c.nodeType != c.ELEMENT_NODE]
                                                for c in list(node.childNodes):
                                                    node.removeChild(c)
                                                for e in sorted(elems, key=lambda e: e.tagName):
                                                    node.appendChild(e)
                                                for o in others:
                                                    node.appendChild(o)
                                        except Exception:
                                            pass
                                    sort_node(dom.documentElement)
                                return dom.toprettyxml(indent="  ")
                            except Exception:
                                return text_in
                        return text_in
                    except Exception:
                        return text_in

                def _process_single_request(idx: int, total_in_seq: int, r_key: str,
                                            r_val: dict, timeout_s: float | None,
                                            effective_retry: dict | None,
                                            response_opts: dict | None,
                                            insecure_eff: bool,
                                            seq_i: int) -> tuple[int, list[str], int]:
                    # Previously this function received already-built arguments: method, full_url,
                    # headers_out, data_bytes. The prepare loop did all resolution upfront.
                    #
                    # Now it receives the raw r_val dict and does all resolution here, just before
                    # the HTTP call. This is required for Capture: { $pattern: "${captured:KEY}" }
                    # fields reference values populated by earlier
                    # requests that have already executed, which isn't possible if resolution
                    # happens upfront for all requests at once.
                    #
                    # resolve_deferred is called with the current captures snapshot so $pattern,
                    # $dynamic(when:request), and $timestamp(when:request) all expand in one pass
                    # with the correct runtime state. $pattern is always request-time, which is
                    # what makes ${captured:KEY} inside a $pattern template work correctly.
                    #
                    # Return value extended from (idx, lines) to (idx, lines, expect_fail_count)
                    # to propagate Expect failures up to the run-level counter.
                    lines: list[str] = []
                    expect_fail_count = 0
                    try:
                        click.echo(f"Running request {idx}/{total_in_seq}: {r_key}")
                    except Exception:
                        pass

                    # Snapshot captures so all refs in this request see a consistent state,
                    # even if another thread is writing captures concurrently.
                    with captures_lock:
                        caps_snap = dict(captured)

                    method = (r_val.get("Method") or "").upper()
                    url_path = r_val.get("URLPath") or ""
                    headers_raw = r_val.get("Headers")
                    body_raw = r_val.get("Body")
                    query_raw = r_val.get("Query")
                    capture_cfg = r_val.get("Capture")
                    expect_cfg = r_val.get("Expect")

                    # Materialize $deferred markers with captures snapshot so $pattern templates
                    # containing ${captured:KEY} resolve to the correct runtime values.
                    headers_res = resolve_deferred(headers_raw, secrets=secrets_map, captures=caps_snap) if headers_raw is not None else None
                    body_res = resolve_deferred(body_raw, secrets=secrets_map, captures=caps_snap) if body_raw is not None else None
                    query_res = resolve_deferred(query_raw, secrets=secrets_map, captures=caps_snap) if query_raw is not None else None
                    if expect_cfg is not None:
                        expect_cfg = resolve_deferred(expect_cfg, secrets=secrets_map, captures=caps_snap)

                    # Build URL
                    base = (url_root or "").rstrip('/')
                    upath = (url_path or "").lstrip('/')
                    full_url = base + ("/" if upath else "") + upath
                    if query_res:
                        qparts = urlparse.urlencode(query_res, doseq=True, safe="/:?")
                        sep = '&' if '?' in full_url else '?'
                        full_url = f"{full_url}{sep}{qparts}"

                    # Build data bytes
                    data_bytes = None
                    if body_res is not None:
                        try:
                            data_bytes = _json.dumps(body_res).encode('utf-8')
                        except Exception:
                            data_bytes = str(body_res).encode('utf-8')

                    # Build headers
                    headers_out: dict = {}
                    if isinstance(headers_res, dict):
                        headers_out.update(headers_res)
                    if data_bytes is not None and not any(h.lower() == 'content-type' for h in headers_out):
                        headers_out['Content-Type'] = 'application/json; charset=utf-8'

                    resolved_request_block = {
                        "Method": method, "URLRoot": url_root, "URLPath": url_path,
                        "Headers": headers_res, "Body": body_res, "Query": query_res,
                        "TimeoutSeconds": timeout_s, "InsecureTLS": insecure_eff,
                    }
                    if response_opts:
                        resolved_request_block["Response"] = response_opts
                    if capture_cfg:
                        resolved_request_block["Capture"] = capture_cfg
                    if expect_cfg:
                        resolved_request_block["Expect"] = expect_cfg

                    start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    lines.append(f"  Request {idx}/{total_in_seq}: {r_key}")
                    lines.append(f"    URL: {_redact_text(full_url)}")
                    lines.append(f"    Start: {start_iso}")
                    seq_name_csv = seq_dir_name
                    req_name_csv = f"req{idx:03d}-{r_key}"
                    y_req = yaml_to_string(_redact_struct(resolved_request_block)).splitlines()
                    lines.append("    Resolved Request:")
                    lines.extend(["      " + ln for ln in y_req])
                    if effective_retry is None:
                        lines.append("    Resolved Retry: Null")
                    else:
                        y_ret = yaml_to_string(effective_retry).splitlines()
                        lines.append("    Resolved Retry:")
                        lines.extend(["      " + ln for ln in y_ret])

                    if dry_run:
                        lines.append("    DRY-RUN: would make request (skipped)")
                        try:
                            _append_result_row(seq_name_csv, req_name_csv, start_iso, -1, 0, 0)
                        except Exception:
                            pass
                        return idx, lines, 0

                    duration_ms = 0
                    resp_text = ""
                    resp_headers: dict = {}
                    status = -1
                    attempts_made = 0
                    try:
                        t0 = time.perf_counter()
                        status, resp_headers, resp_text, attempts_made, req_log = rm.request(
                            method=method,
                            url=full_url,
                            headers=headers_out,
                            body=data_bytes,
                            timeout_s=timeout_s,
                            retry_cfg=effective_retry,
                            insecure_tls=insecure_eff,
                        )
                        t1 = time.perf_counter()
                        duration_ms = int(round((t1 - t0) * 1000))
                        if req_log:
                            for l in req_log.splitlines():
                                lines.append("    " + _redact_text(l))
                        lines.append(f"    Response: HTTP {status}")
                        lines.append(f"    Attempts: {attempts_made}")
                        y_hdr = yaml_to_string(_redact_struct(resp_headers)).splitlines()
                        lines.append("    Response Headers:")
                        lines.extend(["      " + ln for ln in y_hdr])

                        # Determine content-type and extension
                        ct_value = None
                        for hk, hv in (resp_headers or {}).items():
                            if str(hk).lower() == 'content-type':
                                ct_value = str(hv)
                                break
                        ext = 'txt'
                        if isinstance(ct_value, str) and '/' in ct_value:
                            try:
                                subtype = ct_value.split(';', 1)[0].strip().split('/', 1)[1].strip()
                                if subtype:
                                    ext = subtype.lower()
                            except Exception:
                                pass

                        # Capture: extract named values from the response and store them in the
                        # run-level captured dict. Subsequent requests can reference these via
                        # via { $pattern: "${captured:KEY}" } in any field (headers, body, query, expect).
                        if capture_cfg:
                            new_captures = {}
                            for cap_name, cap_path in capture_cfg.items():
                                try:
                                    val = resolve_response_path(cap_path, status, resp_headers, resp_text, duration_ms)
                                    new_captures[cap_name] = val
                                    lines.append(f"    Capture: {cap_name} = {val!r}")
                                except Exception as ce:
                                    lines.append(f"    Capture warning ({cap_name}): {ce}")
                            if new_captures:
                                with captures_lock:
                                    captured.update(new_captures)

                        # Expect: evaluate assertions against the response. Each item is a
                        # single-key dict mapping a response path to a matcher (or shorthand
                        # primitive, treated as equals). Failures are logged with ✗ and the
                        # actual value. All assertions run — no short-circuit on first failure.
                        expect_passed = 0
                        expect_failed_local = 0
                        if expect_cfg:
                            expect_results = evaluate_expect(expect_cfg, status, resp_headers, resp_text, duration_ms)
                            lines.append("    Expect:")
                            for label, passed, detail in expect_results:
                                mark = "✓" if passed else "✗"
                                lines.append(f"      {mark} {label}")
                                if detail:
                                    lines.append(f"    {detail}")
                                if passed:
                                    expect_passed += 1
                                else:
                                    expect_failed_local += 1
                            expect_fail_count = expect_failed_local
                            with captures_lock:
                                run_expect_failures[0] += expect_failed_local

                        # Write response body to file
                        try:
                            resp_out_path = seq_out_dir / f"req{idx:03d}-{r_key}-response.{ext}"
                            text_to_write = _maybe_format_response(resp_text, ct_value, response_opts)
                            with resp_out_path.open('w', encoding='utf-8') as rf:
                                rf.write(text_to_write)
                            lines.append(f"    Response Body: written to {resp_out_path}")
                        except Exception as we:
                            lines.append(f"    Warning: failed to write response body file: {we}")

                        _append_result_row(seq_name_csv, req_name_csv, start_iso, int(status), duration_ms, attempts_made, expect_passed, expect_failed_local)

                        # Accumulate report entry
                        _build_report_entry(seq_i, idx, r_key, method, full_url, headers_out, body_res,
                                            status, duration_ms, resp_headers, resp_text, ct_value,
                                            capture_cfg, captured if capture_cfg else None,
                                            expect_cfg, expect_results if expect_cfg else None)

                    except Exception as he:
                        req_log_err = getattr(he, "request_log", None)
                        if req_log_err:
                            for line in str(req_log_err).splitlines():
                                lines.append("    " + line)
                        lines.append(f"    ERROR: Request failed: {he}")
                        try:
                            t1 = time.perf_counter()
                            duration_ms = int(round((t1 - t0) * 1000))
                        except Exception:
                            pass
                        attempts_fail = getattr(he, "attempts_made", 1)
                        _append_result_row(seq_name_csv, req_name_csv, start_iso, -1, duration_ms,
                                           int(attempts_fail) if isinstance(attempts_fail, (int, float)) else 1)
                        _build_report_entry(seq_i, idx, r_key, method, full_url, headers_out, body_res,
                                            -1, duration_ms, {}, str(he), None,
                                            None, None, None, None)

                    return idx, lines, expect_fail_count

                def _build_report_entry(seq_i, req_i, r_key, method, full_url, headers_out, body_res,
                                        status, duration_ms, resp_headers, resp_text, ct_value,
                                        capture_cfg, captures_at_time, expect_cfg, expect_results):
                    try:
                        entry = {
                            "sort_key": (seq_i, req_i),
                            "r_key": r_key,
                            "method": method,
                            "full_url": _redact_text(full_url),
                            "headers_out": _redact_struct(dict(headers_out or {})),
                            "body_res": body_res,
                            "status": status,
                            "duration_ms": duration_ms,
                            "resp_headers": resp_headers,
                            "resp_text": resp_text,
                            "ct_value": ct_value,
                            "capture_cfg": capture_cfg,
                            "captured_values": {k: captures_at_time.get(k) for k in (capture_cfg or {})} if captures_at_time else None,
                            "expect_cfg": expect_cfg,
                            "expect_results": expect_results,
                        }
                        with report_lock:
                            report_entries.append(entry)
                    except Exception:
                        pass

                # Execute sequentially or concurrently
                s_type = (seq_d.get("Type") or "Sequential").strip()
                total_in_seq = len(prepared_requests)
                from concurrent.futures import ThreadPoolExecutor, as_completed

                conc_limit = seq_d.get("ConcurrencyLimit")
                def _effective_workers() -> int:
                    caps = []
                    if conc_limit:
                        try:
                            caps.append(int(conc_limit))
                        except Exception:
                            pass
                    cap = min(caps) if caps else None
                    if cap is None:
                        return min(8, max(1, total_in_seq))
                    return max(1, min(cap, total_in_seq))

                if s_type.lower() == "concurrent":
                    workers = _effective_workers()
                    _log_redacted(f"  Using concurrency: workers={workers}")
                    outcomes: dict[int, list[str]] = {}
                    next_to_flush = 1
                    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"seq{i:03d}") as ex:
                        futs = []
                        for (idx, r_key, r_val, timeout_s, delay_seconds, effective_retry, response_opts, insecure_eff) in prepared_requests:
                            fut = ex.submit(_process_single_request, idx, total_in_seq, r_key, r_val, timeout_s, effective_retry, response_opts, insecure_eff, i)
                            futs.append(fut)
                        for fut in as_completed(futs):
                            idx, lines, _ = fut.result()
                            outcomes[idx] = lines
                            while next_to_flush in outcomes:
                                _log_redacted("\n".join(outcomes.pop(next_to_flush)))
                                next_to_flush += 1
                else:
                    for (idx, r_key, r_val, timeout_s, delay_seconds, effective_retry, response_opts, insecure_eff) in prepared_requests:
                        _, lines, _ = _process_single_request(idx, total_in_seq, r_key, r_val, timeout_s, effective_retry, response_opts, insecure_eff, i)
                        _log_redacted("\n".join(lines))
                        try:
                            _log_redacted(f"    Delay {delay_seconds if delay_seconds is not None else 0} s")
                            if delay_seconds and delay_seconds > 0:
                                time.sleep(delay_seconds)
                        except Exception:
                            pass

            _log_redacted("=== PayloadStash run finished ===")

            # Write the markdown report. This is a new artifact alongside the existing
            # resolved YAML, run log, and results CSV. It renders one section per request
            # showing request details, response body, captured values, and Expect assertion
            # results. Requests without Expect show as "Executed" with no pass/fail judgment.
            try:
                _write_markdown_report(
                    run_root / f"{config.stem}-report.md",
                    sc_name, config.stem, ts, report_entries,
                )
            except Exception as re_err:
                _log_redacted(f"Warning: failed to write report: {re_err}")

            if run_expect_failures[0] > 0:
                click.echo(f"\n{run_expect_failures[0]} expect assertion(s) failed.")
                sys.exit(1)
        else:
            click.echo("\nOperation Cancelled")
    except Exception:
        click.echo("\nOperation Cancelled")

    sys.exit(0)


@main.command()
@click.option("--name", default="world", help="Name to greet")
def hello(name: str):
    """A trivial demo command to verify installation."""
    click.echo(f"Hello, {name}! This is PayloadStash {__version__}.")

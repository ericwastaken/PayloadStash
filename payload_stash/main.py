import sys
from pathlib import Path
from datetime import datetime, timezone
import click
import yaml

from . import __version__
from .config_schema import validate_config_path, format_validation_error, build_resolved_config_dict


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

            # Initialize results CSV with header
            try:
                import csv
                with results_csv_path.open('w', encoding='utf-8', newline='') as cf:
                    w = csv.writer(cf)
                    w.writerow(["sequence", "request", "timestamp", "status", "duration_ms", "attempts"])
            except Exception as e:
                _log_redacted(f"Warning: failed to initialize results CSV '{results_csv_path}': {e}")

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


            def _append_result_row(seq_name: str, req_name: str, ts_iso: str, status_code: int, duration_ms: int, attempts: int) -> None:
                try:
                    with csv_lock:
                        with results_csv_path.open('a', encoding='utf-8', newline='') as cf:
                            w = _csv.writer(cf)
                            w.writerow([seq_name, req_name, ts_iso, status_code, duration_ms, attempts])
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

                # Prepare all requests for this sequence (resolve and persist to resolved file)
                req_items = seq_d.get("Requests", [])
                prepared_requests: list[tuple[int, str, dict, dict, str, dict, bytes | None, float | None, dict | None]] = []
                # Each tuple: (index, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry)
                for j, req_item in enumerate(req_items, start=1):
                    if not isinstance(req_item, dict) or len(req_item) != 1:
                        _log_redacted(f"  Skipping malformed request at index {j}")
                        continue
                    r_key, r_val = next(iter(req_item.items()))

                    method = (r_val.get("Method") or "").upper()
                    url_path = r_val.get("URLPath") or ""
                    headers = r_val.get("Headers")
                    body = r_val.get("Body")
                    query = r_val.get("Query")
                    # Per-request FlowControl overrides
                    r_flow = r_val.get("FlowControl") or {}
                    timeout_s = r_flow.get("TimeoutSeconds", default_timeout)
                    delay_seconds = r_flow.get("DelaySeconds", default_delay)

                    # Resolve deferred for sections
                    headers_res = resolve_deferred(headers, secrets=secrets_map) if headers is not None else None
                    body_res = resolve_deferred(body, secrets=secrets_map) if body is not None else None
                    query_res = resolve_deferred(query, secrets=secrets_map) if query is not None else None

                    # Update resolved dicts with URLRoot and resolved sections
                    try:
                        resolved_actual["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["URLRoot"] = url_root
                        resolved_redacted["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["URLRoot"] = url_root
                    except Exception:
                        pass
                    if headers_res is not None:
                        resolved_actual["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Headers"] = headers_res
                        resolved_redacted["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Headers"] = _redact_struct(headers_res)
                    if body_res is not None:
                        resolved_actual["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Body"] = body_res
                        resolved_redacted["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Body"] = _redact_struct(body_res)
                    if query_res is not None:
                        resolved_actual["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Query"] = query_res
                        resolved_redacted["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Query"] = _redact_struct(query_res)

                    # Overwrite the resolved file on disk after resolving this request
                    try:
                        write_yaml_file(resolved_path, resolved_redacted)
                    except Exception as we:
                        _log_redacted(f"  Warning: failed to update resolved file after {r_key}: {we}")

                    # Build URL
                    base = (url_root or "").rstrip('/')
                    path = (url_path or "").lstrip('/')
                    full_url = base + ("/" if path else "") + path
                    if query_res:
                        qparts = urlparse.urlencode(query_res, doseq=True, safe="/:?")
                        sep = '&' if ('?' in full_url) else '?'
                        full_url = f"{full_url}{sep}{qparts}"

                    # Prepare body
                    data_bytes = None
                    if body_res is not None:
                        try:
                            data_bytes = json.dumps(body_res).encode('utf-8')
                        except Exception:
                            data_bytes = str(body_res).encode('utf-8')

                    # Prepare headers
                    headers_out = {}
                    if isinstance(headers_res, dict):
                        headers_out.update(headers_res)
                    if data_bytes is not None and not any(h.lower() == 'content-type' for h in headers_out.keys()):
                        headers_out['Content-Type'] = 'application/json; charset=utf-8'

                    # Effective Retry (already precedence-resolved in resolved config building)
                    effective_retry = r_val.get("Retry") if isinstance(r_val, dict) else None

                    # Response formatting options
                    response_opts = None
                    try:
                        ro = r_val.get("Response") if isinstance(r_val, dict) else None
                        if isinstance(ro, dict):
                            response_opts = {k: v for k, v in ro.items() if k in ("PrettyPrint", "Sort")}
                    except Exception:
                        response_opts = None

                    resolved_request_block = {
                        "Method": method,
                        "URLRoot": url_root,
                        "URLPath": url_path,
                        "Headers": headers_res,
                        "Body": body_res,
                        "Query": query_res,
                        "TimeoutSeconds": timeout_s,
                    }
                    if response_opts is not None:
                        resolved_request_block["Response"] = response_opts

                    prepared_requests.append((j, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry))

                # Helper to format and execute a single request, returning grouped log lines
                from .utility import yaml_to_string
                import json as _json

                def _process_single_request(idx: int, total_in_seq: int, r_key: str,
                                            method: str, full_url: str, headers_out: dict, data_bytes: bytes | None,
                                            timeout_s: float | None, effective_retry: dict | None,
                                            resolved_request_block: dict) -> tuple[int, list[str]]:
                    lines: list[str] = []
                    try:
                        click.echo(f"Running request {idx}/{total_in_seq}: {r_key}")
                    except Exception:
                        pass
                    lines.append(f"  Request {idx}/{total_in_seq}: {r_key}")
                    lines.append(f"    URL: {_redact_text(full_url)}")
                    # Capture start timestamp (UTC, ISO8601 Z) and log it
                    start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    lines.append(f"    Start: {start_iso}")
                    seq_name_csv = f"{seq_dir_name}"
                    req_name_csv = f"req{idx:03d}-{r_key}"
                    # Log Resolved Request
                    y_req = yaml_to_string(_redact_struct(resolved_request_block)).splitlines()
                    lines.append("    Resolved Request:")
                    lines.extend(["      " + ln for ln in y_req])
                    # Resolved Retry
                    if effective_retry is None:
                        lines.append("    Resolved Retry: Null")
                    else:
                        y_ret = yaml_to_string(effective_retry).splitlines()
                        lines.append("    Resolved Retry:")
                        lines.extend(["      " + ln for ln in y_ret])

                    if dry_run:
                        lines.append("    DRY-RUN: would make request (skipped)")
                        # Write CSV row for dry-run with status -1 and duration 0
                        try:
                            _append_result_row(seq_name_csv, req_name_csv, start_iso, -1, 0, 0)
                        except Exception:
                            pass
                        return idx, lines

                    # Execute request
                    try:
                        t0 = time.perf_counter()
                        status, resp_headers, resp_text, attempts_made, req_log = rm.request(
                            method=method,
                            url=full_url,
                            headers=headers_out,
                            body=data_bytes,
                            timeout_s=timeout_s,
                            retry_cfg=effective_retry,
                        )
                        if req_log:
                            for l in req_log.splitlines():
                                lines.append("    " + _redact_text(l))
                        lines.append(f"    Response: HTTP {status}")
                        lines.append(f"    Attempts: {attempts_made}")
                        # Response headers
                        y_hdr = yaml_to_string(_redact_struct(resp_headers)).splitlines()
                        lines.append("    Response Headers:")
                        lines.extend(["      " + ln for ln in y_hdr])
                        # Write body to file
                        try:
                            ct_value = None
                            for hk, hv in (resp_headers or {}).items():
                                try:
                                    if str(hk).lower() == 'content-type':
                                        ct_value = str(hv)
                                        break
                                except Exception:
                                    continue
                            ext = 'txt'
                            if isinstance(ct_value, str) and ct_value:
                                try:
                                    ct_main = ct_value.split(';', 1)[0].strip()
                                    if '/' in ct_main:
                                        subtype = ct_main.split('/', 1)[1].strip()
                                        if subtype:
                                            ext = subtype.lower()
                                except Exception:
                                    pass

                            # Optional pretty-print / sort based on Response settings and content-type
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
                                    # JSON handling
                                    if ct_main and (ct_main.endswith('/json') or ct_main == 'application/json'):
                                        try:
                                            from rich.console import Console
                                            from rich.json import JSON as RichJSON
                                            import io as _io
                                            # If sort requested, we need to ensure keys are sorted; RichJSON supports sort_keys
                                            s = _io.StringIO()
                                            console = Console(file=s, no_color=True, force_jupyter=False, force_terminal=False, color_system=None, width=120)
                                            # RichJSON can take a JSON string directly
                                            rj = RichJSON(text_in, indent=2, sort_keys=sort_flag)
                                            console.print(rj)
                                            return s.getvalue().rstrip() + "\n"
                                        except Exception:
                                            # Fallback to standard formatting
                                            import json as _json2
                                            try:
                                                obj = _json2.loads(text_in)
                                                return _json2.dumps(obj, indent=2, sort_keys=sort_flag, ensure_ascii=False) + "\n"
                                            except Exception:
                                                return text_in
                                    # XML handling
                                    if ct_main and (ct_main in ('application/xml', 'text/xml') or ct_main.endswith('+xml')):
                                        try:
                                            from xml.dom import minidom as _minidom
                                            dom = _minidom.parseString(text_in.encode('utf-8'))
                                            if bool(resp_cfg.get("Sort")):
                                                # Sort attributes and child elements by tag name (simple, shallow sort)
                                                def sort_node(node):
                                                    try:
                                                        if node.nodeType == node.ELEMENT_NODE:
                                                            # sort attributes
                                                            if node.hasAttributes():
                                                                attrs = node.attributes
                                                                names = sorted([attrs.item(i).name for i in range(attrs.length)])
                                                                # rebuild attribute order by cloning
                                                                for n in names:
                                                                    v = attrs.get(n).value
                                                                    attrs.removeNamedItem(n)
                                                                    attrs.setNamedItem(node.ownerDocument.createAttribute(n))
                                                                    attrs.get(n).value = v
                                                            # sort children: elements by tagName; recurse
                                                            children = [c for c in node.childNodes]
                                                            for c in children:
                                                                sort_node(c)
                                                            # reorder element children
                                                            elems = [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE]
                                                            others = [c for c in node.childNodes if c.nodeType != c.ELEMENT_NODE]
                                                            elems_sorted = sorted(elems, key=lambda e: e.tagName)
                                                            # Remove all children then append in new order preserving non-elements order
                                                            for c in list(node.childNodes):
                                                                node.removeChild(c)
                                                            for e in elems_sorted:
                                                                node.appendChild(e)
                                                            for o in others:
                                                                node.appendChild(o)
                                                    except Exception:
                                                        pass
                                                sort_node(dom.documentElement)
                                            pretty_xml = dom.toprettyxml(indent="  ")
                                            # minidom adds xml declaration; keep as-is
                                            return pretty_xml
                                        except Exception:
                                            return text_in
                                    return text_in
                                except Exception:
                                    return text_in

                            resp_out_name = f"req{idx:03d}-{r_key}-response.{ext}"
                            resp_out_path = seq_out_dir / resp_out_name
                            # Derive Response config from resolved request block
                            resp_cfg = resolved_request_block.get("Response") if isinstance(resolved_request_block, dict) else None
                            text_to_write = _maybe_format_response(resp_text, ct_value, resp_cfg)
                            with resp_out_path.open('w', encoding='utf-8') as rf:
                                rf.write(text_to_write)
                            lines.append(f"    Response Body: written to {resp_out_path}")
                        except Exception as we:
                            lines.append(f"    Warning: failed to write response body file: {we}")
                        # Record success to CSV
                        try:
                            t1 = time.perf_counter()
                            duration_ms = int(round((t1 - t0) * 1000))
                            _append_result_row(seq_name_csv, req_name_csv, start_iso, int(status), duration_ms, attempts_made)
                        except Exception:
                            pass
                    except Exception as he:
                        # Any internal request logs captured by RequestManager on error
                        try:
                            req_log = getattr(he, "request_log", None)
                        except Exception:
                            req_log = None
                        if req_log:
                            for line in str(req_log).splitlines():
                                lines.append("    " + line)
                        lines.append(f"    ERROR: Request failed: {he}")
                        # Record failure to CSV (-1 status)
                        try:
                            t1 = time.perf_counter()
                            duration_ms = int(round((t1 - t0) * 1000))
                            attempts_fail = getattr(he, "attempts_made", 1)
                            _append_result_row(seq_name_csv, req_name_csv, start_iso, -1, duration_ms, int(attempts_fail) if isinstance(attempts_fail, (int, float)) else 1)
                        except Exception:
                            pass
                    return idx, lines

                # Execute sequentially or concurrently
                s_type = (seq_d.get("Type") or "Sequential").strip()
                total_in_seq = len(prepared_requests)
                from concurrent.futures import ThreadPoolExecutor, as_completed

                # Determine workers for concurrent type
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
                        for (idx, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry) in prepared_requests:
                            method = (r_val.get("Method") or "").upper()
                            fut = ex.submit(_process_single_request, idx, total_in_seq, r_key, method, full_url, headers_out, data_bytes, timeout_s, effective_retry, resolved_request_block)
                            futs.append(fut)
                        for fut in as_completed(futs):
                            idx, lines = fut.result()
                            outcomes[idx] = lines
                            while next_to_flush in outcomes:
                                _log_redacted("\n".join(outcomes.pop(next_to_flush)))
                                next_to_flush += 1
                    # No sequence-level delay per clarified semantics
                else:
                    # Sequential
                    for (idx, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry) in prepared_requests:
                        method = (r_val.get("Method") or "").upper()
                        _, lines = _process_single_request(idx, total_in_seq, r_key, method, full_url, headers_out, data_bytes, timeout_s, effective_retry, resolved_request_block)
                        _log_redacted("\n".join(lines))
                        # Respect FlowControl delay between requests only
                        r_flow = (r_val.get("FlowControl") or {})
                        delay_seconds = r_flow.get("DelaySeconds", default_delay)
                        try:
                            _log_redacted(f"    Delay {delay_seconds if delay_seconds is not None else 0} s")
                            if delay_seconds and delay_seconds > 0:
                                time.sleep(delay_seconds)
                        except Exception:
                            pass
                # No delay when advancing to next sequence per clarified semantics

            _log_redacted("=== PayloadStash run finished ===")
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

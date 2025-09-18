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
def validate(config: Path, writeresolved: bool):
    """Validate a YAML CONFIG file against the PayloadStash schema.

    When --writeResolved is provided, writes a fully-resolved copy named
    '<original-stem>-resolved.yml' in the same directory as the CONFIG file.
    """
    try:
        cfg = validate_config_path(config)
        # If we reach here, validation passed
        sc_name = cfg.StashConfig.Name
        sequences = len(cfg.StashConfig.Sequences)
        click.echo(f"OK: {config} is a valid PayloadStash config. Name='{sc_name}', Sequences={sequences}")

        if writeresolved:
            resolved = build_resolved_config_dict(cfg)

            class NoAliasDumper(yaml.SafeDumper):
                def ignore_aliases(self, data):
                    return True

            out_path = config.with_name(f"{config.stem}-resolved.yml")
            try:
                with out_path.open('w', encoding='utf-8') as f:
                    yaml.dump(resolved, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
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

def run(config: Path, out_dir: Path, dry_run: bool, yes: bool):
    # 1) Basic argument validation
    if out_dir is None:
        click.echo("Error: --out is required", err=True)
        sys.exit(9)

    # 2) Validate config and build resolved dict (resolve-time expansion)
    try:
        cfg = validate_config_path(config)
        resolved = build_resolved_config_dict(cfg)
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
            yaml.dump(resolved, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True)
    except Exception as e:
        click.echo(f"Error: failed to write resolved config: {e}", err=True)
        sys.exit(9)

    # Prepare log file path
    log_path = run_root / f"{config.stem}-run.log"

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

            # Pull defaults (including URLRoot) and flow control
            sc_resolved = resolved.get("StashConfig", {})
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
            for i, seq_d in enumerate(seq_dicts, start=1):
                s_name = seq_d.get("Name")
                s_type = seq_d.get("Type")
                s_conc = seq_d.get("ConcurrencyLimit")
                msg = f"Processing sequence {i}/{total_seq}: {s_name} (Type={s_type}"
                if s_conc is not None:
                    msg += f", ConcurrencyLimit={s_conc}"
                msg += ")"
                click.echo(msg)
                write_log(log_path, msg)

                # Create per-sequence output directory (seqNNN-Name)
                seq_dir_name = f"seq{i:03d}-{s_name}"
                seq_out_dir = run_root / seq_dir_name
                try:
                    seq_out_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    write_log(log_path, f"  Warning: failed to create sequence directory '{seq_out_dir}': {e}")

                # Prepare all requests for this sequence (resolve and persist to resolved file)
                req_items = seq_d.get("Requests", [])
                prepared_requests: list[tuple[int, str, dict, dict, str, dict, bytes | None, float | None, dict | None]] = []
                # Each tuple: (index, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry)
                for j, req_item in enumerate(req_items, start=1):
                    if not isinstance(req_item, dict) or len(req_item) != 1:
                        write_log(log_path, f"  Skipping malformed request at index {j}")
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
                    headers_res = resolve_deferred(headers) if headers is not None else None
                    body_res = resolve_deferred(body) if body is not None else None
                    query_res = resolve_deferred(query) if query is not None else None

                    # Update in-memory resolved dict with URLRoot and resolved sections
                    try:
                        resolved["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["URLRoot"] = url_root
                    except Exception:
                        pass
                    if headers_res is not None:
                        resolved["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Headers"] = headers_res
                    if body_res is not None:
                        resolved["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Body"] = body_res
                    if query_res is not None:
                        resolved["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["Query"] = query_res

                    # Overwrite the resolved file on disk after resolving this request
                    try:
                        write_yaml_file(resolved_path, resolved)
                    except Exception as we:
                        write_log(log_path, f"  Warning: failed to update resolved file after {r_key}: {we}")

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

                    resolved_request_block = {
                        "Method": method,
                        "URLRoot": url_root,
                        "URLPath": url_path,
                        "Headers": headers_res,
                        "Body": body_res,
                        "Query": query_res,
                        "TimeoutSeconds": timeout_s,
                    }

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
                    lines.append(f"    URL: {full_url}")
                    # Log Resolved Request
                    y_req = yaml_to_string(resolved_request_block).splitlines()
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
                        return idx, lines

                    # Execute request
                    try:
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
                                lines.append("    " + l)
                        lines.append(f"    Response: HTTP {status}")
                        lines.append(f"    Attempts: {attempts_made}")
                        # Response headers
                        y_hdr = yaml_to_string(resp_headers).splitlines()
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
                            resp_out_name = f"req{idx:03d}-{r_key}-response.{ext}"
                            resp_out_path = seq_out_dir / resp_out_name
                            with resp_out_path.open('w', encoding='utf-8') as rf:
                                rf.write(resp_text)
                            lines.append(f"    Response Body: written to {resp_out_path}")
                        except Exception as we:
                            lines.append(f"    Warning: failed to write response body file: {we}")
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
                    write_log(log_path, f"  Using concurrency: workers={workers}")
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
                                write_log(log_path, "\n".join(outcomes.pop(next_to_flush)))
                                next_to_flush += 1
                    # No sequence-level delay per clarified semantics
                else:
                    # Sequential
                    for (idx, r_key, resolved_request_block, headers_out, full_url, r_val, data_bytes, timeout_s, effective_retry) in prepared_requests:
                        method = (r_val.get("Method") or "").upper()
                        _, lines = _process_single_request(idx, total_in_seq, r_key, method, full_url, headers_out, data_bytes, timeout_s, effective_retry, resolved_request_block)
                        write_log(log_path, "\n".join(lines))
                        # Respect FlowControl delay between requests only
                        r_flow = (r_val.get("FlowControl") or {})
                        delay_seconds = r_flow.get("DelaySeconds", default_delay)
                        try:
                            write_log(log_path, f"    Delay {delay_seconds if delay_seconds is not None else 0} s")
                            if delay_seconds and delay_seconds > 0:
                                time.sleep(delay_seconds)
                        except Exception:
                            pass
                # No delay when advancing to next sequence per clarified semantics

            write_log(log_path, "=== PayloadStash run finished ===")
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

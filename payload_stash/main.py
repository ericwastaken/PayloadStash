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
@click.option("--max-workers", type=int, required=False, help="Optional upper bound for concurrency across the whole run.")
@click.option("--dry-run", is_flag=True, help="Resolve request configs and log actions, but do not actually make HTTP requests.")
def run(config: Path, out_dir: Path, max_workers: int | None, dry_run: bool):
    # 1) Basic argument validation
    if out_dir is None:
        click.echo("Error: --out is required", err=True)
        sys.exit(9)
    if max_workers is not None:
        try:
            int(max_workers)
        except Exception:
            click.echo("Error: --max-workers must be an integer", err=True)
            sys.exit(9)
        if max_workers <= 0:
            click.echo("Error: --max-workers must be > 0", err=True)
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
    if max_workers is not None:
        click.echo(f"  Max Workers:     {max_workers}")
    click.echo(f"  Output folder:   {run_root}")
    click.echo(f"  Resolved config: {resolved_path}")
    click.echo(f"  Log file:        {log_path}")
    if dry_run:
        click.echo("  Mode:            DRY-RUN (no HTTP calls)")

    # 6) User confirmation prompt
    try:
        click.echo(" Continue? [y/N]: ", nl=False)
        resp = click.get_text_stream('stdin').readline().strip().lower()
        if resp in ("y", "yes"):
            click.echo(f"\nProcessing {sc_name}")

            from .utility import start_run_log, write_log, log_yaml, write_yaml_file
            from .config_utility import resolve_deferred
            import time
            from urllib import request as urlrequest
            from urllib import parse as urlparse
            import json
            import socket

            start_run_log(log_path, ts, sc_name, resolved_path, max_workers)

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

                # Only Sequential supported for now (issue says do not implement Retry yet and no concurrency requirement here)
                req_items = seq_d.get("Requests", [])
                for j, req_item in enumerate(req_items, start=1):
                    # req_item is like { Key: {Method, URLPath, Headers, Body, Query, FlowControl?, Retry?} }
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
                    # Find and replace in resolved structure
                    try:
                        resolved["StashConfig"]["Sequences"][i-1]["Requests"][j-1][r_key]["URLRoot"] = url_root
                    except Exception:
                        # Ensure key path exists; if not, ignore silently
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
                        # Flatten query to str mapping; handle lists
                        qparts = urlparse.urlencode(query_res, doseq=True, safe="/:?")
                        sep = '&' if ('?' in full_url) else '?'
                        full_url = f"{full_url}{sep}{qparts}"

                    # Prepare body
                    data_bytes = None
                    if body_res is not None:
                        try:
                            data_bytes = json.dumps(body_res).encode('utf-8')
                        except Exception:
                            # Fallback: attempt to send as str
                            data_bytes = str(body_res).encode('utf-8')

                    # Prepare headers
                    headers_out = {}
                    if isinstance(headers_res, dict):
                        headers_out.update(headers_res)
                    if data_bytes is not None and not any(h.lower() == 'content-type' for h in headers_out.keys()):
                        headers_out['Content-Type'] = 'application/json; charset=utf-8'

                    # Log the prepared request
                    click.echo(f"  Request {j}/{len(req_items)}: {r_key}")
                    write_log(log_path, f"  Request {j}/{len(req_items)}: {r_key}")
                    write_log(log_path, f"    URL: {full_url}")

                    if dry_run:
                        write_log(log_path, "    DRY-RUN: would make request (skipped)")
                        log_yaml(log_path, "    Resolved Request:", {r_key: {"Method": method, "URLRoot": url_root, "URLPath": url_path, "Headers": headers_res, "Body": body_res, "Query": query_res, "TimeoutSeconds": timeout_s}}, indent=4)
                    else:
                        # Log resolved request before making the call
                        log_yaml(log_path, "    Resolved Request:", {r_key: {"Method": method, "URLRoot": url_root, "URLPath": url_path, "Headers": headers_res, "Body": body_res, "Query": query_res, "TimeoutSeconds": timeout_s}}, indent=4)
                        # Make HTTP request with timeout, catch timeout as failure
                        try:
                            req_obj = urlrequest.Request(full_url, data=data_bytes, headers=headers_out, method=method)
                            timeout_arg = None
                            if isinstance(timeout_s, int) and timeout_s > 0:
                                timeout_arg = float(timeout_s)
                            # Use socket timeout handling
                            with urlrequest.urlopen(req_obj, timeout=timeout_arg) as resp:
                                status = getattr(resp, 'status', None) or resp.getcode()
                                resp_headers = dict(resp.headers.items()) if hasattr(resp, 'headers') else {}
                                try:
                                    resp_body = resp.read()
                                except Exception:
                                    resp_body = b""
                                # Attempt to decode as text
                                try:
                                    resp_text = resp_body.decode('utf-8', errors='replace')
                                except Exception:
                                    resp_text = str(resp_body)
                                write_log(log_path, f"    Response: HTTP {status}")
                                log_yaml(log_path, "    Response Headers:", resp_headers, indent=6)
                                # Write response body to a file instead of logging it
                                try:
                                    # Decide file extension based on Content-Type header (use subtype, e.g., application/json -> json)
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
                                    resp_out_name = f"seq{i:02d}-req{j:02d}-{r_key}-response.{ext}"
                                    resp_out_path = run_root / resp_out_name
                                    with resp_out_path.open('w', encoding='utf-8') as rf:
                                        rf.write(resp_text)
                                    write_log(log_path, f"    Response Body: written to {resp_out_path}")
                                except Exception as we:
                                    write_log(log_path, f"    Warning: failed to write response body file: {we}")
                        except socket.timeout as te:
                            write_log(log_path, f"    ERROR: Request timed out after {timeout_s}s: {te}")
                        except Exception as he:
                            write_log(log_path, f"    ERROR: Request failed: {he}")

                    # Respect FlowControl delay between requests
                    try:
                        write_log(log_path, f"    Delay {delay_seconds if delay_seconds is not None else 0} s")
                        if delay_seconds and delay_seconds > 0:
                            time.sleep(delay_seconds)
                    except Exception:
                        pass

                # Delay when advancing to next sequence as well
                try:
                    if delay_seconds and delay_seconds > 0:
                        time.sleep(delay_seconds)
                except Exception:
                    pass

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

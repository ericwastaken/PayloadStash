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


@main.command(help="Run a PayloadStash config. Phase 1: validate, resolve, and write the resolved config; print a summary.")
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path), help="Output directory root for run artifacts.")
@click.option("--max-workers", type=int, required=False, help="Optional upper bound for concurrency across the whole run.")
def run(config: Path, out_dir: Path, max_workers: int | None):
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
    # Timestamp like 2025-09-17T15-42-10Z per README (dashes in the time portion)
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
    click.echo("-- Stopping here by design (phase 1). No HTTP requests were sent.")

    # 6) User confirmation prompt
    try:
        # Print exactly as requested (leading space, no colon)
        click.echo(" Continue? [y/N]", nl=False)
        resp = click.get_text_stream('stdin').readline().strip().lower()
        if resp in ("y", "yes"):
            click.echo(f"\nProcessing {sc_name}")
        else:
            click.echo("\nOperation Cancelled")
    except Exception:
        # In non-interactive contexts, treat as cancelled
        click.echo("\nOperation Cancelled")

    sys.exit(0)


@main.command()
@click.option("--name", default="world", help="Name to greet")
def hello(name: str):
    """A trivial demo command to verify installation."""
    click.echo(f"Hello, {name}! This is PayloadStash {__version__}.")

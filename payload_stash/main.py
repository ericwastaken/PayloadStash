import sys
from pathlib import Path
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


@main.command()
@click.option("--name", default="world", help="Name to greet")
def hello(name: str):
    """A trivial demo command to verify installation."""
    click.echo(f"Hello, {name}! This is PayloadStash {__version__}.")

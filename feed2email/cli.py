"""feed2email CLI entry point."""

from pathlib import Path

import click

from feed2email.db.database import Database
from feed2email.core.config_manager import ConfigManager
from feed2email.models import VALID_CONFIG_KEYS


@click.group()
@click.option(
    "--db",
    envvar="FEED2EMAIL_DB",
    type=click.Path(),
    default=None,
    help="Path to the SQLite database file (overrides FEED2EMAIL_DB env var).",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose output.")
@click.pass_context
def cli(ctx, db, verbose):
    """feed2email - Monitor RSS/Atom feeds and deliver new items via email."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db) if db else None
    ctx.obj["verbose"] = verbose


def _get_database(ctx: click.Context) -> Database:
    """Create and initialize a Database instance from the context."""
    db_path = ctx.obj["db_path"]
    db = Database(path=db_path)
    db.initialize()
    return db


@cli.command()
@click.argument("key", required=False, default=None)
@click.argument("value", required=False, default=None)
@click.option(
    "--unset", is_flag=True, default=False, help="Remove the configuration value for KEY."
)
@click.pass_context
def config(ctx, key, value, unset):
    """Get or set configuration values.

    With no arguments: list all config.
    With KEY only: display the current value for KEY.
    With KEY and VALUE: set KEY to VALUE.
    With KEY --unset: remove the value for KEY.

    """
    db = _get_database(ctx)
    try:
        cm = ConfigManager(db)

        if key is None:
            if unset:
                raise click.ClickException("KEY is required when using --unset.")
            all_config = cm.list_all()
            if not all_config:
                click.echo("No configuration values set.")
            else:
                for k, v in all_config.items():
                    click.echo(f"{k} = {v}")
            return

        if key not in VALID_CONFIG_KEYS:
            valid_keys = ", ".join(VALID_CONFIG_KEYS)
            raise click.ClickException(f"Invalid key '{key}'. Valid keys: {valid_keys}")

        if unset:
            if value is not None:
                raise click.ClickException("Cannot specify both a VALUE and --unset.")
            ok, error = cm.unset(key)
            if not ok:
                raise click.ClickException(error)
            if cm.get(key) is None:
                click.echo(f"Unset {key}")
            return

        if value is None:
            current = cm.get(key)
            if current is None:
                click.echo(f"{key}: not set")
            else:
                click.echo(f"{key} = {current}")
            return

        ok, error = cm.set(key, value)
        if not ok:
            raise click.ClickException(f"Invalid value for '{key}': {error}")

        click.echo(f"Set {key} = {value}")
    finally:
        db.close()

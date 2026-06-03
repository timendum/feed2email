"""feed2email CLI entry point."""

import logging
import sys
from pathlib import Path

import click

from feed2email.config_manager import ConfigManager
from feed2email.db import Database
from feed2email.feed_manager import FeedError, FeedManager
from feed2email.models import VALID_CONFIG_KEYS

# Commands that do NOT require setup to be complete.
_EXEMPT_COMMANDS = ("config", "init")


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


def _setup_guard(ctx: click.Context) -> None:
    """Abort with a helpful message if Required_Configuration is incomplete.

    Exempt commands (config, init) and --help invocations bypass this check.
    """
    # Determine the invoked subcommand name
    invoked = ctx.info_name
    if invoked in _EXEMPT_COMMANDS:
        return

    db = _get_database(ctx)
    try:
        cm = ConfigManager(db)
        if not cm.is_setup_complete():
            raise click.ClickException(
                "Setup is incomplete\nRun 'feed2email init' to complete setup."
            )
    finally:
        db.close()


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
                raise click.ClickException(error or "Unknown error")
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


@cli.command()
@click.pass_context
def init(ctx):
    """Interactively configure all required settings."""
    db = _get_database(ctx)
    try:
        cm = ConfigManager(db)

        # Prompts for required keys
        _prompts = [
            ("smtp.from", "From email address"),
            ("default-recipient", "Default recipient email"),
            ("smtp.host", "SMTP host"),
            ("smtp.port", "SMTP port"),
            ("smtp.encryption", "SMTP connection encryption (none/starttls/ssl)"),
        ]

        for key, label in _prompts:
            current = cm.get(key)
            while True:
                default_display = f" [{current}]" if current else ""
                value = click.prompt(
                    f"{label}{default_display}", default=current or "", show_default=False
                )
                if not value and current:
                    # User pressed Enter to keep the existing value
                    break
                if not value:
                    click.echo("  A value is required.")
                    continue
                ok, error = cm.validate_value(key, value)
                if not ok:
                    click.echo(f"  Invalid: {error}")
                    continue
                cm.set(key, value)
                break

        # Optional keys
        _optional_prompts = [
            ("smtp.user", "SMTP username (press Enter to skip)"),
            ("smtp.password", "SMTP password (press Enter to skip)"),
        ]

        for key, label in _optional_prompts:
            current = cm.get(key)
            hide = key == "smtp.password"
            default_hint = f" [{'***' if hide and current else current or ''}]" if current else ""
            value = click.prompt(
                f"{label}{default_hint}",
                default="",
                show_default=False,
                hide_input=hide,
            )
            if value:
                ok, error = cm.validate_value(key, value)
                if not ok:
                    click.echo(f"  Invalid: {error}. Skipping SMTP authentication.")
                    break
                else:
                    cm.set(key, value)
            # If empty, leave unchanged

        click.echo("Setup complete. You're ready to use feed2email.")
    finally:
        db.close()


@cli.command()
@click.argument("url")
@click.option("--recipient", "-r", default=None, help="Recipient email address for this feed.")
@click.option(
    "--dedup-key",
    type=click.Choice(["id", "link", "title"]),
    default="id",
    help="Field used for deduplication (default: id).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "html"]),
    default="text",
    help="Email format (default: text).",
)
@click.option(
    "--item-date",
    is_flag=True,
    default=False,
    help="Use item publication date as email Date header.",
)
@click.option(
    "--mark-read",
    is_flag=True,
    default=False,
    help="Mark all existing items as read (default: all but the latest are marked).",
)
@click.pass_context
def add(ctx, url, recipient, dedup_key, fmt, item_date, mark_read):
    """Add a feed URL to monitor.

    URL is the RSS/Atom feed URL to add. The feed is fetched immediately to
    verify it is reachable and parseable. By default, all existing items except
    the most recent one are marked as read so you receive only the latest item
    on the next run. Use --mark-read to mark ALL items as read instead.
    """
    _setup_guard(ctx)
    db = _get_database(ctx)
    try:
        fm = FeedManager(db)
        feed = fm.add_feed(
            url=url,
            recipient=recipient,
            dedup_key=dedup_key,
            format=fmt,
            item_date=item_date,
            mark_read=mark_read,
        )
        click.echo(f"Added feed #{feed.id}: {feed.url}")
    except FeedError as e:
        raise click.ClickException(str(e)) from None
    finally:
        db.close()


@cli.command()
@click.argument("feed_ref")
@click.pass_context
def remove(ctx, feed_ref):
    """Remove a feed by URL or Feed_ID.

    FEED_REF is the feed URL or numeric Feed_ID.
    """
    _setup_guard(ctx)
    db = _get_database(ctx)
    try:
        fm = FeedManager(db)
        # Try integer Feed_ID
        ref: str | int = feed_ref
        if feed_ref.isdigit():
            ref = int(feed_ref)
        fm.remove_feed(ref)
        click.echo(f"Removed feed: {feed_ref}")
    except FeedError as e:
        raise click.ClickException(str(e)) from None
    finally:
        db.close()


@cli.command("list")
@click.pass_context
def list_feeds(ctx):
    """List all configured feeds."""
    _setup_guard(ctx)
    db = _get_database(ctx)
    try:
        fm = FeedManager(db)
        feeds = fm.list_feeds()
        if not feeds:
            click.echo("No feeds configured.")
            return
        for feed in feeds:
            recipient_display = feed.recipient or "(default)"
            paused_display = "paused" if feed.paused else "active"
            click.echo(
                f"#{feed.id}  {feed.url}  recipient={recipient_display}  "
                f"dedup_key={feed.dedup_key}  {paused_display}"
            )
    finally:
        db.close()


@cli.command()
@click.argument("feed_ref")
@click.pass_context
def pause(ctx, feed_ref):
    """Pause a feed by URL or Feed_ID.

    FEED_REF is the feed URL or numeric Feed_ID.
    """
    _setup_guard(ctx)
    db = _get_database(ctx)
    try:
        fm = FeedManager(db)
        ref: str | int = feed_ref
        if feed_ref.isdigit():
            ref = int(feed_ref)
        message = fm.pause_feed(ref)
        click.echo(message)
    except FeedError as e:
        raise click.ClickException(str(e)) from None
    finally:
        db.close()


@cli.command()
@click.argument("feed_ref")
@click.pass_context
def unpause(ctx, feed_ref):
    """Unpause a feed by URL or Feed_ID.

    FEED_REF is the feed URL or numeric Feed_ID.
    """
    _setup_guard(ctx)
    db = _get_database(ctx)
    try:
        fm = FeedManager(db)
        ref: str | int = feed_ref
        if feed_ref.isdigit():
            ref = int(feed_ref)
        message = fm.unpause_feed(ref)
        click.echo(message)
    except FeedError as e:
        raise click.ClickException(str(e)) from None
    finally:
        db.close()


@cli.command()
@click.option(
    "--dry-run", is_flag=True, default=False, help="Show what would be sent without sending."
)
@click.pass_context
def run(ctx, dry_run):
    """Fetch all feeds and deliver new items via email.

    With --dry-run, display what would be sent without actually sending
    emails or recording items as seen.
    """
    _setup_guard(ctx)

    verbose = ctx.obj.get("verbose", False)
    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(message)s")

    db = _get_database(ctx)
    try:
        cm = ConfigManager(db)
        fm = FeedManager(db)

        feeds = fm.list_feeds()
        if not feeds:
            click.echo("No feeds configured.")
            sys.exit(0)

        if not dry_run:
            missing_keys = cm.get_missing_smtp_keys()
            if missing_keys:
                raise click.ClickException(
                    f"SMTP configuration incomplete. Missing: {', '.join(missing_keys)}\n"
                    "Run 'feed2email config' to set the required SMTP parameters."
                )

        # Get user-agent from config or use default
        user_agent = cm.get("user-agent") or "feed2email"

        # Instantiate dependencies
        from feed2email.email_sender import EmailSender
        from feed2email.feed_fetcher import FeedFetcher
        from feed2email.template_renderer import TemplateRenderer

        fetcher = FeedFetcher(user_agent=user_agent)

        mailer = None
        if not dry_run:
            smtp_config = cm.get_smtp()
            if smtp_config is None:
                raise click.ClickException(
                    "SMTP is not configured. Run 'feed2email config' to set it up."
                )
            mailer = EmailSender(smtp_config)

        renderer = TemplateRenderer()

        from feed2email.runner import Runner

        runner = Runner(db=db, fetcher=fetcher, mailer=mailer, renderer=renderer)
        result = runner.run(dry_run=dry_run)

        exit_code = runner.compute_exit_code(result)
        sys.exit(exit_code)
    finally:
        db.close()

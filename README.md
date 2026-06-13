# feed2email

A command-line tool that monitors RSS/Atom feeds and delivers new items via email. It stores state in a local SQLite database and sends mail over SMTP.

## Installation

Requires Python 3.13 or later. Published on [PyPI](https://pypi.org/project/feed2email/).

```sh
uv tool install feed2email
```

This installs `feed2email` as a standalone CLI tool managed by uv. You can also use pip:

```sh
pip install feed2email
```

## Quick start

Run the setup wizard to configure SMTP and a default recipient:

```sh
feed2email init
```

Add a feed:

```sh
feed2email add https://example.com/feed.xml
```

Fetch new items and send them:

```sh
feed2email run
```

By default, when you add a feed all existing items except the most recent one are marked as read. The next `run` delivers only the latest item plus anything published after that point.

## Commands

```
feed2email init          Interactive setup for SMTP and recipient
feed2email config        Get, set, unset, or list configuration values
feed2email add URL       Add a feed (fetches and validates immediately)
feed2email edit REF      Edit a feed's settings (URL, dedup key, format, etc.)
feed2email remove REF    Remove a feed by URL or ID
feed2email list          List all configured feeds
feed2email pause REF     Pause delivery for a feed
feed2email unpause REF   Resume delivery for a feed
feed2email run           Fetch feeds and deliver new items
```

REF is either the numeric feed ID or its URL.

### Global options

`--db PATH` overrides the database location (also settable via the `FEED2EMAIL_DB` environment variable). The default path is determined by `platformdirs.user_data_dir("feed2email")`.

`--verbose` / `-v` enables INFO-level log output.

### Adding feeds

```sh
feed2email add https://example.com/rss.xml \
  --recipient alice@example.com \
  --dedup-key link \
  --format html \
  --item-date
```

`--recipient` sets a feed-specific recipient (falls back to `default-recipient` from config).
`--dedup-key` chooses which field prevents duplicate delivery: `id` (default), `link`, or `title`.
`--format` selects email body format: `text` (default) or `html`.
`--item-date` uses the item's publication date as the email Date header.
`--mark-read` marks all existing items as read instead of keeping the latest unread.

### Configuration

Required keys: `smtp.host`, `smtp.port`, `smtp.from`, `smtp.encryption`, `default-recipient`.

Optional keys: `smtp.user`, `smtp.password`, `user-agent`, `retry.max`, `retry.backoff`, `host-delay`.

```sh
feed2email config smtp.host mail.example.com
feed2email config smtp.port 587
feed2email config smtp.encryption starttls
feed2email config                          # list all
feed2email config smtp.password --unset    # remove a value
```

#### Retry

By default, HTTP requests to fetch feeds are not retried.  
You can enable automatic retries for transient errors with exponential backoff:

```sh
feed2email config retry.max 3        # retry up to 3 times (default: 0, no retry)
feed2email config retry.backoff 0.8  # backoff factor in seconds (default: 0.5)
```

Check [requests documentation](https://requests.readthedocs.io/en/latest/user/advanced/#example-automatic-retries)
for more informations.

#### Host delay

If you have multiple feeds on the same host, 
you can set a delay (in seconds) between requests to avoid hammering the server:

```sh
feed2email config host-delay 2      # wait 2 seconds between requests to the same host
feed2email config host-delay 0.5    # fractional seconds are supported
feed2email config host-delay 0      # disable (default)
```

### Dry run

```sh
feed2email run --dry-run
```

Shows what would be sent without delivering mail or updating state.

## How it works

On each `run`, for each active feed it fetches the feed, deduplicates items against previously seen entries, renders an email (plain text or HTML via Jinja2), sends it over SMTP, and records the item as seen.

Exit codes: 0 = all feeds processed, 1 = partial failure (some feeds or items failed), 2 = total failure.

## Development

For contributors and developers working on feed2email itself.

```sh
git clone https://github.com/timendum/feed2email.git
cd feed2email
uv sync                # install all dependencies including dev extras
```

The project uses [uv](https://docs.astral.sh/uv/) for dependency management and [just](https://github.com/casey/just) as a task runner.

```sh
just test              # run tests (pytest)
just lint              # lint (ruff)
just fmt               # format (ruff)
just typecheck         # type check (ty)
just check             # all of the above
```

Tests live in `tests/` and mirror the source layout. External calls (HTTP, SMTP) are mocked; databases use temporary paths via pytest's `tmp_path` fixture.


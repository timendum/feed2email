"""Run last. End-to-end test: configure → add feed → run."""

import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from feed2email.config_manager import ConfigManager
from feed2email.db import Database
from feed2email.email_sender import EmailSender
from feed2email.feed_fetcher import FeedFetcher
from feed2email.feed_manager import FeedManager
from feed2email.runner import Runner
from feed2email.template_renderer import TemplateRenderer

FEED_DIR = Path(__file__).parent / "feeds"

FEED_FILES = sorted(f.name for f in FEED_DIR.iterdir() if f.is_file())


class _QuietHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves from FEED_DIR and suppresses logging."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FEED_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def feed_server(monkeypatch):
    """Spin up a local HTTP server serving test feed files."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = HTTPServer(("127.0.0.1", 0), _QuietHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield port
    server.shutdown()
    thread.join()


def _setup_db(tmp_path: Path) -> Database:
    """Create and initialize a temporary database."""
    db = Database(path=tmp_path / "feed2email.db")
    db.initialize()
    return db


def _configure(config_mgr: ConfigManager) -> None:
    """Set up all required config values."""
    config_values = {
        "smtp.from": "sender@example.com",
        "default-recipient": "recipient@example.com",
        "smtp.host": "localhost",
        "smtp.port": "1025",
        "smtp.encryption": "none",
    }
    for key, value in config_values.items():
        ok, error = config_mgr.set(key, value)
        assert ok, f"config set {key} failed: {error}"


@pytest.mark.parametrize("feed_file", FEED_FILES, ids=FEED_FILES)
def test_e2e_add_run(tmp_path, feed_server, feed_file):
    url = f"http://127.0.0.1:{feed_server}/{feed_file}"

    db = _setup_db(tmp_path)
    try:
        config_mgr = ConfigManager(db)
        feed_mgr = FeedManager(db)

        # init
        _configure(config_mgr)
        assert config_mgr.is_setup_complete()
        smtp_config = config_mgr.get_smtp()
        assert smtp_config is not None
        mailer = EmailSender(smtp_config)

        # add
        feed = feed_mgr.add_feed(url)
        assert feed.url == url

        # list
        feeds = feed_mgr.list_feeds()
        assert len(feeds) == 1

        # run 1
        fetcher = FeedFetcher()
        renderer = TemplateRenderer()

        with patch("feed2email.email_sender.smtplib.SMTP") as mock_smtp_class:
            mock_conn = MagicMock()
            mock_smtp_class.return_value = mock_conn

            runner = Runner(db=db, fetcher=fetcher, mailer=mailer, renderer=renderer)
            result = runner.run()

        assert result.feeds_failed == 0, f"Feed {feed_file} failed during run"
        assert mock_conn.sendmail.called, f"SMTP.sendmail was never called for {feed_file}"
        for call in mock_conn.sendmail.call_args_list:
            _from, to, _msg_str = call[0]
            assert to == "recipient@example.com"

        # run 2
        with patch("feed2email.email_sender.smtplib.SMTP") as mock_smtp_class_2:
            mock_conn_2 = MagicMock()
            mock_smtp_class_2.return_value = mock_conn_2

            runner2 = Runner(db=db, fetcher=fetcher, mailer=mailer, renderer=renderer)
            result2 = runner2.run()

        assert result2.feeds_failed == 0
        assert not mock_conn_2.sendmail.called, (
            f"No email should be sent on second run for {feed_file} (all items seen)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

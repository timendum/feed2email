"""Unit tests for the Runner class."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from feed2email.db import Database
from feed2email.models import EmailMessage, Feed, FeedItem, FetchResult, RunResult, SendResult
from feed2email.runner import Runner


@pytest.fixture
def mock_db(db: Database) -> Database:
    """Return a real initialized DB with a default-recipient configured."""
    db.set_config("default-recipient", "user@example.com")
    return db


@pytest.fixture
def mock_fetcher():
    """Create a mock FeedFetcher."""
    return MagicMock()


@pytest.fixture
def mock_mailer():
    """Create a mock EmailSender."""
    return MagicMock()


@pytest.fixture
def mock_renderer():
    """Create a mock TemplateRenderer."""
    renderer = MagicMock()
    renderer.make_subject.return_value = "Test Subject"
    renderer.render.return_value = "Test Body"
    return renderer


@pytest.fixture
def runner(mock_db, mock_fetcher, mock_mailer, mock_renderer):
    """Create a Runner instance with mocked dependencies."""
    return Runner(
        db=mock_db,
        fetcher=mock_fetcher,
        mailer=mock_mailer,
        renderer=mock_renderer,
    )


def _make_feed(db: Database, url: str = "http://example.com/feed.xml", **kwargs) -> Feed:
    """Helper to add a feed to the database and return it."""
    return db.add_feed(
        url=url,
        recipient=kwargs.get("recipient", None),
        dedup_key=kwargs.get("dedup_key", "link"),
        format=kwargs.get("format", "text"),
        item_date=kwargs.get("item_date", False),
    )


def _make_item(**kwargs) -> FeedItem:
    """Helper to create a FeedItem with defaults."""
    return FeedItem(
        id=kwargs.get("id", "item-1"),
        title=kwargs.get("title", "Test Item"),
        link=kwargs.get("link", "http://example.com/item-1"),
        content=kwargs.get("content", "<p>Content</p>"),
        published=kwargs.get("published", datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)),
    )


class TestRunnerNoFeeds:
    """Tests for when no feeds are configured."""

    def test_no_feeds_returns_zero_counts(self, runner):
        result = runner.run()
        assert result.feeds_processed == 0
        assert result.feeds_failed == 0
        assert result.items_sent == 0
        assert result.items_failed == 0

    def test_no_feeds_exit_code_is_zero(self, runner):
        result = runner.run()
        assert runner.compute_exit_code(result) == 0


class TestRunnerFetchFailure:
    """Tests for feed fetch failures."""

    def test_fetch_failure_increments_feeds_failed(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db)
        mock_fetcher.fetch.return_value = FetchResult(
            success=False, items=[], feed_title="", error="Connection timeout"
        )
        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()
        assert result.feeds_failed == 1
        assert result.feeds_processed == 0

    def test_fetch_failure_continues_to_next_feed(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, url="http://example.com/feed1.xml")
        _make_feed(mock_db, url="http://example.com/feed2.xml")

        items = [_make_item()]
        mock_fetcher.fetch.side_effect = [
            FetchResult(success=False, items=[], feed_title="", error="Timeout"),
            FetchResult(success=True, items=items, feed_title="Feed 2"),
        ]
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.feeds_failed == 1
        assert result.feeds_processed == 1
        assert result.items_sent == 1

    def test_all_feeds_fail_exit_code_2(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db, url="http://example.com/feed1.xml")
        _make_feed(mock_db, url="http://example.com/feed2.xml")

        mock_fetcher.fetch.return_value = FetchResult(
            success=False, items=[], feed_title="", error="Timeout"
        )

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert runner.compute_exit_code(result) == 2


class TestRunnerDeduplication:
    """Tests for deduplication logic."""

    def test_seen_items_are_skipped(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db, dedup_key="id")
        mock_db.mark_seen(feed.id, "item-1")

        items = [_make_item(id="item-1")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_sent == 0
        mock_mailer.send.assert_not_called()

    def test_unseen_items_are_sent(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db)

        items = [_make_item(link="item-1")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_sent == 1
        mock_mailer.send.assert_called_once()

    def test_items_missing_dedup_key_are_skipped(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, dedup_key="id")

        items = [_make_item(id=None)]  # Missing the dedup key
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_sent == 0
        mock_mailer.send.assert_not_called()

    def test_sent_items_are_marked_seen(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db, dedup_key="id")

        items = [_make_item(id="new-item")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        assert mock_db.is_seen(feed.id, items[0].id)

    def test_sent_items_are_marked_seen_link(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        feed = _make_feed(mock_db, dedup_key="link")

        items = [_make_item(link="http://example.com/new-item")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        assert mock_db.is_seen(feed.id, items[0].link)

    def test_dedup_by_link(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db, dedup_key="link")
        mock_db.mark_seen(feed.id, "http://example.com/item-1")

        items = [_make_item(link="http://example.com/item-1")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_sent == 0

    def test_dedup_by_title(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db, dedup_key="title")
        mock_db.mark_seen(feed.id, "Test Item")

        items = [_make_item(title="Test Item")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_sent == 0


class TestRunnerSMTPFailure:
    """Tests for SMTP failure handling."""

    def test_smtp_failure_increments_items_failed(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=False, error="SMTP refused")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_failed == 1
        assert result.items_sent == 0

    def test_smtp_failure_continues_to_next_item(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db)

        items = [_make_item(id="item-1"), _make_item(id="item-2")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.side_effect = [
            SendResult(success=False, error="SMTP refused"),
            SendResult(success=True),
        ]

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.items_failed == 1
        assert result.items_sent == 1


class TestRunnerDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_does_not_send_email(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run(dry_run=True)

        mock_mailer.send.assert_not_called()
        assert result.items_sent == 1

    def test_dry_run_does_not_record_seen(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db)

        items = [_make_item(id="dry-item")]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run(dry_run=True)

        assert not mock_db.is_seen(feed.id, "dry-item")

    def test_dry_run_prints_item_info(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer, capsys
    ):
        _make_feed(mock_db, url="http://example.com/feed.xml")

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_renderer.make_subject.return_value = "My Subject"

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run(dry_run=True)

        captured = capsys.readouterr()
        assert "user@example.com" in captured.out
        assert "My Subject" in captured.out
        assert "http://example.com/feed.xml" in captured.out

    def test_dry_run_works_without_mailer(self, mock_db, mock_fetcher, mock_renderer):
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, None, mock_renderer)
        result = runner.run(dry_run=True)

        assert result.items_sent == 1

    def test_dry_run_exit_code_0_on_success(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run(dry_run=True)

        assert runner.compute_exit_code(result) == 0

    def test_dry_run_exit_code_2_all_feeds_fail(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db)

        mock_fetcher.fetch.return_value = FetchResult(
            success=False, items=[], feed_title="", error="Timeout"
        )

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run(dry_run=True)

        assert runner.compute_exit_code(result) == 2


class TestRunnerDateHeader:
    """Tests for Date header computation."""

    def test_item_date_disabled_uses_current_time(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, item_date=False)

        item = _make_item(published=datetime(2020, 1, 1, tzinfo=UTC))
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=[item], feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        # The date should be close to now, not 2020
        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.date.year >= 2024

    def test_item_date_enabled_uses_item_published(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, item_date=True)

        pub_date = datetime(2023, 6, 15, 10, 30, 0, tzinfo=UTC)
        item = _make_item(published=pub_date)
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=[item], feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.date == pub_date

    def test_item_date_enabled_no_published_falls_back(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, item_date=True)

        item = _make_item(published=None)
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=[item], feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.date.year >= 2024

    def test_item_date_naive_datetime_gets_utc(
        self, mock_db, mock_fetcher, mock_mailer, mock_renderer
    ):
        _make_feed(mock_db, item_date=True)

        # Naive datetime (no tzinfo)
        naive_date = datetime(2023, 3, 1, 8, 0, 0)  # noqa: DTZ001
        item = _make_item(published=naive_date)
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=[item], feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.date.tzinfo == UTC
        assert sent_message.date.year == 2023


class TestRunnerRecipient:
    """Tests for recipient resolution."""

    def test_per_feed_recipient_is_used(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db, recipient="specific@example.com")

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.recipient == "specific@example.com"

    def test_default_recipient_fallback(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db, recipient=None)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.recipient == "user@example.com"

    def test_no_recipient_available_skips_feed(self, db, mock_fetcher, mock_mailer, mock_renderer):
        """If no per-feed recipient and no default-recipient, skip the feed."""
        # db without default-recipient
        _ = db.add_feed(
            url="http://example.com/feed.xml",
            recipient=None,
            dedup_key="id",
            format="text",
            item_date=False,
        )

        runner = Runner(db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        assert result.feeds_failed == 1
        mock_fetcher.fetch.assert_not_called()


class TestRunnerExitCodes:
    """Tests for exit code computation."""

    def test_exit_code_0_no_work(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult()
        assert runner.compute_exit_code(result) == 0

    def test_exit_code_0_all_success(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult(feeds_processed=2, items_sent=5)
        assert runner.compute_exit_code(result) == 0

    def test_exit_code_1_partial_failure(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult(feeds_processed=2, feeds_failed=1, items_sent=3, items_failed=1)
        assert runner.compute_exit_code(result) == 1

    def test_exit_code_2_total_failure(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult(feeds_failed=2)
        assert runner.compute_exit_code(result) == 2

    def test_exit_code_2_no_items_sent_with_failures(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult(feeds_processed=1, items_failed=3)
        assert runner.compute_exit_code(result) == 2

    def test_exit_code_1_some_items_sent_some_failed(self):
        runner = Runner(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = RunResult(feeds_processed=1, items_sent=2, items_failed=1)
        assert runner.compute_exit_code(result) == 1


class TestRunnerEmailMessage:
    """Tests for email message construction."""

    def test_email_includes_feed_metadata(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db, url="http://example.com/feed.xml")

        item = _make_item(id="item-123", link="http://example.com/item-123")
        mock_fetcher.fetch.return_value = FetchResult(
            success=True, items=[item], feed_title="My Feed"
        )
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.feed_id == feed.url
        assert sent_message.item_url == item.link
        assert sent_message.item_id == item.id

    def test_email_includes_user_agent(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.user_agent == "feed2email"

    def test_custom_user_agent_from_config(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        mock_db.set_config("user-agent", "my-custom-agent/1.0")
        _make_feed(mock_db)

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.user_agent == "my-custom-agent/1.0"

    def test_html_format_sets_content_type(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db, format="html")

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.content_type == "text/html"

    def test_text_format_sets_content_type(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        _make_feed(mock_db, format="text")

        items = [_make_item()]
        mock_fetcher.fetch.return_value = FetchResult(success=True, items=items, feed_title="Test")
        mock_mailer.send.return_value = SendResult(success=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        runner.run()

        sent_message: EmailMessage = mock_mailer.send.call_args[0][0]
        assert sent_message.content_type == "text/plain"


class TestRunnerPausedFeeds:
    """Tests for paused feed handling."""

    def test_paused_feeds_are_skipped(self, mock_db, mock_fetcher, mock_mailer, mock_renderer):
        feed = _make_feed(mock_db)
        mock_db.set_feed_paused(feed.id, paused=True)

        runner = Runner(mock_db, mock_fetcher, mock_mailer, mock_renderer)
        result = runner.run()

        mock_fetcher.fetch.assert_not_called()
        assert result.feeds_processed == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

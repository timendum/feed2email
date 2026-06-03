"""Unit tests for FeedManager."""

import pytest

from feed2email.db import Database
from feed2email.feed_manager import FeedError, FeedManager
from feed2email.models import FeedItem, FetchResult


class TestAddFeed:
    def test_add_feed_with_valid_url_and_recipient(self, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
        )
        assert feed.url == "https://example.com/feed.xml"
        assert feed.recipient == "user@example.com"
        assert feed.dedup_key is not None
        assert feed.format is not None
        assert feed.item_date is False
        assert feed.paused is False

    def test_add_feed_with_custom_options(self, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            dedup_key="link",
            format="html",
            item_date=True,
        )
        assert feed.dedup_key == "link"
        assert feed.format == "html"
        assert feed.item_date is True

    def test_add_feed_invalid_url_rejected(self, patched_manager: FeedManager):
        with pytest.raises(FeedError, match="Invalid URL"):
            patched_manager.add_feed(url="ftp://bad.com/feed", recipient="user@example.com")

    def test_add_feed_invalid_email_rejected(self, patched_manager: FeedManager):
        with pytest.raises(FeedError, match="Invalid email address"):
            patched_manager.add_feed(url="https://example.com/feed.xml", recipient="notanemail")

    def test_add_feed_duplicate_url_rejected(self, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        with pytest.raises(FeedError, match="Feed already exists"):
            patched_manager.add_feed(
                url="https://example.com/feed.xml", recipient="user@example.com"
            )

    def test_add_feed_uses_default_recipient(self, db: Database, patched_manager: FeedManager):
        db.set_config("default-recipient", "default@example.com")
        feed = patched_manager.add_feed(url="https://example.com/feed.xml")
        # Feed stores None; default is resolved at run time
        assert feed.recipient is None

    def test_add_feed_no_recipient_stores_none(self, patched_manager: FeedManager):
        """Without a recipient, the feed stores None — resolution happens at run time."""
        feed = patched_manager.add_feed(url="https://example.com/feed.xml")
        assert feed.recipient is None

    def test_add_feed_explicit_recipient_overrides_default(
        self, db: Database, patched_manager: FeedManager
    ):
        db.set_config("default-recipient", "default@example.com")
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="specific@example.com",
        )
        assert feed.recipient == "specific@example.com"

    def test_add_feed_mark_read_marks_all_items_as_seen(
        self, db: Database, patched_manager: FeedManager
    ):
        items = [
            FeedItem(
                id="item1", title="Title 1", link="http://a.com/1", content=None, published=None
            ),
            FeedItem(
                id="item2", title="Title 2", link="http://a.com/2", content=None, published=None
            ),
        ]
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=True, items=items, feed_title="Test Feed"
        )

        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            mark_read=True,
            dedup_key="link",
        )

        for item in items:
            assert db.is_seen(feed.id, str(item.link))

    def test_add_feed_default_marks_all_but_latest_as_seen(
        self, db: Database, patched_manager: FeedManager
    ):
        """Without --mark-read, all items except the first (latest) are marked as seen."""
        items = [
            FeedItem(
                id="item1", title="Title 1", link="http://a.com/1", content=None, published=None
            ),
            FeedItem(
                id="item2", title="Title 2", link="http://a.com/2", content=None, published=None
            ),
            FeedItem(
                id="item3", title="Title 3", link="http://a.com/3", content=None, published=None
            ),
        ]
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=True, items=items, feed_title="Test Feed"
        )

        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            mark_read=False,
            dedup_key="link",
        )

        # First item (latest) should NOT be marked as seen
        assert not db.is_seen(feed.id, "http://a.com/1")
        # Remaining items should be marked as seen
        assert db.is_seen(feed.id, "http://a.com/2")
        assert db.is_seen(feed.id, "http://a.com/3")

    def test_add_feed_single_item_default_marks_none(
        self, db: Database, patched_manager: FeedManager
    ):
        """With a single item and no --mark-read, nothing is marked as seen."""
        items = [
            FeedItem(
                id="item1", title="Title 1", link="http://a.com/1", content=None, published=None
            ),
        ]
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=True, items=items, feed_title="Test Feed"
        )

        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            mark_read=False,
            dedup_key="link",
        )

        assert not db.is_seen(feed.id, "http://a.com/1")

    def test_add_feed_fetch_failure_raises(self, patched_manager: FeedManager):
        """If the feed cannot be fetched, add_feed raises FeedError."""
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=False, items=[], feed_title="", error="Timeout"
        )

        with pytest.raises(FeedError, match="Failed to fetch feed"):
            patched_manager.add_feed(
                url="https://example.com/feed.xml",
                recipient="user@example.com",
            )

    def test_add_feed_mark_read_skips_items_missing_dedup_key(
        self, db: Database, patched_manager: FeedManager
    ):
        items = [
            FeedItem(
                id="item1", title="Title 1", link="http://a.com/1", content=None, published=None
            ),
            FeedItem(id=None, title="Title 2", link="http://a.com/2", content=None, published=None),
            FeedItem(id="", title="Title 3", link="http://a.com/3", content=None, published=None),
        ]
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=True, items=items, feed_title="Test Feed"
        )

        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            mark_read=True,
            dedup_key="id",
        )

        # Only item1 should be marked as seen
        assert db.is_seen(feed.id, "item1")
        assert not db.is_seen(feed.id, "")

    def test_add_feed_mark_read_with_link_dedup_key(
        self, db: Database, patched_manager: FeedManager
    ):
        items = [
            FeedItem(
                id="item1", title="Title 1", link="http://a.com/1", content=None, published=None
            ),
            FeedItem(id="item2", title="Title 2", link=None, content=None, published=None),
        ]
        patched_manager._fetcher.fetch.return_value = FetchResult(
            success=True, items=items, feed_title="Test Feed"
        )

        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            dedup_key="link",
            mark_read=True,
        )

        assert db.is_seen(feed.id, "http://a.com/1")
        # item2 has no link, should be skipped
        assert not db.is_seen(feed.id, "")


class TestRemoveFeed:
    """Tests for FeedManager.remove_feed()."""

    def test_remove_feed_by_url(self, db: Database, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        patched_manager.remove_feed("https://example.com/feed.xml")
        assert db.get_feed("https://example.com/feed.xml") is None

    def test_remove_feed_by_id_str(self, db: Database, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml", recipient="user@example.com"
        )
        patched_manager.remove_feed(str(feed.id))
        assert db.get_feed(str(feed.id)) is None

    def test_remove_feed_by_id_int(self, db: Database, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml", recipient="user@example.com"
        )
        patched_manager.remove_feed(feed.id)
        assert db.get_feed(feed.id) is None

    def test_remove_feed_not_found_raises(self, patched_manager: FeedManager):
        with pytest.raises(FeedError, match="Feed not found"):
            patched_manager.remove_feed("https://nonexistent.com/feed.xml")


class TestListFeeds:
    """Tests for FeedManager.list_feeds()."""

    def test_list_feeds_empty(self, patched_manager: FeedManager):
        assert patched_manager.list_feeds() == []

    def test_list_feeds_returns_all_in_order(self, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://a.com/feed", recipient="user@example.com")
        patched_manager.add_feed(url="https://b.com/feed", recipient="user@example.com")
        patched_manager.add_feed(url="https://c.com/feed", recipient="user@example.com")

        feeds = patched_manager.list_feeds()
        assert len(feeds) == 3
        assert feeds[0].url == "https://a.com/feed"
        assert feeds[1].url == "https://b.com/feed"
        assert feeds[2].url == "https://c.com/feed"

    def test_list_feeds_includes_paused(self, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://a.com/feed", recipient="user@example.com")
        patched_manager.add_feed(url="https://b.com/feed", recipient="user@example.com")
        patched_manager.pause_feed("https://b.com/feed")

        feeds = patched_manager.list_feeds()
        assert len(feeds) == 2
        assert feeds[1].paused is True


class TestPauseFeed:
    """Tests for FeedManager.pause_feed()."""

    def test_pause_active_feed(self, db: Database, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        msg = patched_manager.pause_feed("https://example.com/feed.xml")
        assert "paused" in msg.lower()

        feed = db.get_feed("https://example.com/feed.xml")
        assert feed is not None
        assert feed.paused is True

    def test_pause_already_paused_feed(self, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        patched_manager.pause_feed("https://example.com/feed.xml")
        msg = patched_manager.pause_feed("https://example.com/feed.xml")
        assert "already paused" in msg.lower()

    def test_pause_feed_by_id_int(self, db: Database, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml", recipient="user@example.com"
        )
        msg = patched_manager.pause_feed(feed.id)
        assert "paused" in msg.lower()

        updated = db.get_feed(feed.id)
        assert updated is not None
        assert updated.paused is True

    def test_pause_nonexistent_feed_raises(self, patched_manager: FeedManager):
        with pytest.raises(FeedError, match="Feed not found"):
            patched_manager.pause_feed("https://nonexistent.com/feed.xml")


class TestUnpauseFeed:
    """Tests for FeedManager.unpause_feed()."""

    def test_unpause_paused_feed(self, db: Database, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        patched_manager.pause_feed("https://example.com/feed.xml")
        msg = patched_manager.unpause_feed("https://example.com/feed.xml")
        assert "unpaused" in msg.lower()

        feed = db.get_feed("https://example.com/feed.xml")
        assert feed is not None
        assert feed.paused is False

    def test_unpause_already_active_feed(self, patched_manager: FeedManager):
        patched_manager.add_feed(url="https://example.com/feed.xml", recipient="user@example.com")
        msg = patched_manager.unpause_feed("https://example.com/feed.xml")
        assert "already active" in msg.lower()

    def test_unpause_feed_by_id_int(self, db: Database, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml", recipient="user@example.com"
        )
        patched_manager.pause_feed(feed.id)
        msg = patched_manager.unpause_feed(feed.id)
        assert "unpaused" in msg.lower()

        updated = db.get_feed(feed.id)
        assert updated is not None
        assert updated.paused is False

    def test_unpause_nonexistent_feed_raises(self, patched_manager: FeedManager):
        with pytest.raises(FeedError, match="Feed not found"):
            patched_manager.unpause_feed("https://nonexistent.com/feed.xml")


class TestResolveRecipient:
    """Tests for FeedManager.resolve_recipient() — run-time recipient resolution."""

    def test_feed_manager_uses_default_user_agent(self, db: Database):
        manager = FeedManager(db)
        assert manager._fetcher._session.headers["User-Agent"] == "feed2email"

    def test_feed_manager_uses_custom_user_agent_from_config(self, db: Database):
        db.set_config("user-agent", "MyCustomBot/1.0")
        manager = FeedManager(db)
        assert manager._fetcher._session.headers["User-Agent"] == "MyCustomBot/1.0"

    def test_resolve_explicit_recipient(self, patched_manager: FeedManager):
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="explicit@example.com",
        )
        assert patched_manager.resolve_recipient(feed) == "explicit@example.com"

    def test_resolve_falls_back_to_default(self, db: Database, patched_manager: FeedManager):
        db.set_config("default-recipient", "default@example.com")
        feed = patched_manager.add_feed(url="https://example.com/feed.xml")
        assert feed.recipient is None
        assert patched_manager.resolve_recipient(feed) == "default@example.com"

    def test_resolve_no_recipient_no_default_raises(
        self, db: Database, patched_manager: FeedManager
    ):
        db.set_config("default-recipient", "default@example.com")
        feed = patched_manager.add_feed(url="https://example.com/feed.xml")
        # Remove the default-recipient after adding the feed
        assert db.connection is not None
        db.connection.execute("DELETE FROM config WHERE key = 'default-recipient'")
        db.connection.commit()
        with pytest.raises(FeedError, match="No recipient for feed"):
            patched_manager.resolve_recipient(feed)

    def test_changing_default_affects_feeds_without_explicit_recipient(
        self, db: Database, patched_manager: FeedManager
    ):
        db.set_config("default-recipient", "old@example.com")
        feed = patched_manager.add_feed(url="https://example.com/feed.xml")
        assert patched_manager.resolve_recipient(feed) == "old@example.com"

        # Change the default
        db.set_config("default-recipient", "new@example.com")
        assert patched_manager.resolve_recipient(feed) == "new@example.com"

    def test_explicit_recipient_not_affected_by_default_change(
        self, db: Database, patched_manager: FeedManager
    ):
        db.set_config("default-recipient", "default@example.com")
        feed = patched_manager.add_feed(
            url="https://example.com/feed.xml",
            recipient="specific@example.com",
        )
        db.set_config("default-recipient", "changed@example.com")
        assert patched_manager.resolve_recipient(feed) == "specific@example.com"

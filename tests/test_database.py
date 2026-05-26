"""Tests for the Database class."""

import sqlite3
from pathlib import Path

import pytest

from feed2email.db import Database, _default_db_path
from feed2email.models import Feed


def add_feed(db: Database) -> Feed:
    return db.add_feed("https://example.com/feed.xml", "u@e.com", "id", "text", False)


class TestDatabaseInit:
    def test_default_path_uses_platformdirs(self):
        path = _default_db_path()
        assert "feed2email" in str(path)
        assert path.name == "feed2email.db"

    def test_custom_path(self, tmp_path: Path):
        db_path = tmp_path / "custom.db"
        db = Database(path=db_path)
        assert db.path == db_path

    def test_creates_parent_directories(self, tmp_path: Path):
        db_path = tmp_path / "nested" / "dirs" / "feed2email.db"
        db = Database(path=db_path)
        db.initialize()
        assert db_path.exists()
        db.close()

    def test_default_path_when_none(self):
        db = Database(path=None)
        assert db.path == _default_db_path()


class TestSchemaInitialization:
    def test_creates_tables(self, db: Database):
        for table in ("feeds", "seen_items", "config"):
            cursor = db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            assert cursor.fetchone() is not None

    def test_foreign_keys_enabled(self, db: Database):
        cursor = db.connection.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        assert result[0] == 1

    def test_wal_mode_enabled(self, db: Database):
        cursor = db.connection.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        assert result[0] == "wal"

    def test_double_initialization(self, db: Database):
        cursor = db.connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
        assert cursor.fetchone()[0] >= 3

    def test_seen_items_delete_cascade(self, db: Database):
        db.connection.execute(
            "INSERT INTO feeds (url, recipient) VALUES (?, ?)",
            ("https://example.com/feed.xml", "user@example.com"),
        )
        db.connection.commit()

        cursor = db.connection.execute("SELECT id FROM feeds")
        feed_id = cursor.fetchone()[0]

        db.connection.execute(
            "INSERT INTO seen_items (feed_id, dedup_value) VALUES (?, ?)",
            (feed_id, "item-1"),
        )
        db.connection.commit()

        # Delete
        db.connection.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        db.connection.commit()

        cursor = db.connection.execute(
            "SELECT count(*) FROM seen_items WHERE feed_id = ?", (feed_id,)
        )
        assert cursor.fetchone()[0] == 0


class TestLocking:
    def test_lock(self, db: Database):
        assert db.acquire_lock() is True
        db.release_lock()

    def test_double_lock(self, db: Database):
        assert db.acquire_lock() is True
        assert db.acquire_lock() is True
        db.release_lock()

    def test_lock_blocked(self, tmp_path: Path):
        db_path = tmp_path / "test.db"

        db1 = Database(path=db_path)
        db1.initialize()
        assert db1.acquire_lock() is True

        db2 = Database(path=db_path)
        assert db2.acquire_lock() is False

        db1.release_lock()
        db1.close()
        db2.close()

    def test_release_lock(self, tmp_path: Path):
        db_path = tmp_path / "test.db"

        db1 = Database(path=db_path)
        db1.initialize()
        assert db1.acquire_lock() is True
        db1.release_lock()

        db2 = Database(path=db_path)
        assert db2.acquire_lock() is True
        db2.release_lock()

        db1.close()
        db2.close()

    def test_close_releases_lock(self, tmp_path: Path):
        db_path = tmp_path / "test.db"

        db1 = Database(path=db_path)
        db1.initialize()
        assert db1.acquire_lock() is True
        db1.close()

        db2 = Database(path=db_path)
        assert db2.acquire_lock() is True
        db2.release_lock()
        db2.close()

    def test_release_without_lock(self, db: Database):
        db.release_lock()  # No error


class TestFeed:
    def test_add_feed(self, db: Database):
        feed = db.add_feed(
            url="https://example.com/feed.xml",
            recipient="user@example.com",
            dedup_key="id",
            format="text",
            item_date=False,
        )

        assert feed.url == "https://example.com/feed.xml"
        assert feed.recipient == "user@example.com"
        assert feed.dedup_key == "id"
        assert feed.format == "text"
        assert feed.item_date is False
        assert feed.paused is False
        assert feed.id >= 1
        assert feed.created_at is not None

    def test_add_feed_all_params_required(self, db: Database):
        feed = db.add_feed(
            url="https://example.com/feed2.xml",
            recipient="other@example.com",
            dedup_key="link",
            format="html",
            item_date=True,
        )

        assert feed.url == "https://example.com/feed2.xml"
        assert feed.recipient == "other@example.com"
        assert feed.dedup_key == "link"
        assert feed.format == "html"
        assert feed.item_date is True
        assert feed.id >= 1
        assert feed.created_at is not None

    def test_add_feed_duplicate(self, db: Database):
        add_feed(db)
        with pytest.raises(sqlite3.IntegrityError):
            add_feed(db)

    def test_remove_feed_by_id_str(self, db: Database):
        feed = add_feed(db)
        result = db.remove_feed(str(feed.id))

        assert result is True
        assert db.get_feed(str(feed.id)) is None

    def test_remove_feed_by_id_int(self, db: Database):
        feed = add_feed(db)
        result = db.remove_feed(feed.id)

        assert result is True
        assert db.get_feed(feed.id) is None

    def test_remove_feed_by_url(self, db: Database):
        add_feed(db)
        result = db.remove_feed("https://example.com/feed.xml")

        assert result is True
        assert db.get_feed("https://example.com/feed.xml") is None

    def test_remove_false(self, db: Database):
        result = db.remove_feed("https://nonexistent.com/feed.xml")
        assert result is False

    def test_remove_cascades(self, db: Database):
        feed = add_feed(db)
        db.connection.execute(
            "INSERT INTO seen_items (feed_id, dedup_value) VALUES (?, ?)",
            (feed.id, "item-1"),
        )
        db.connection.execute(
            "INSERT INTO seen_items (feed_id, dedup_value) VALUES (?, ?)",
            (feed.id, "item-2"),
        )
        db.connection.commit()

        db.remove_feed(feed.id)

        cursor = db.connection.execute(
            "SELECT count(*) FROM seen_items WHERE feed_id = ?", (feed.id,)
        )
        assert cursor.fetchone()[0] == 0

    def test_get_feeds_empty(self, db: Database):
        feeds = db.get_feeds()
        assert feeds == []

    def test_get_feeds(self, db: Database):
        db.add_feed("https://a.com/feed", "a@a.com", "id", "text", False)
        feed2 = db.add_feed("https://b.com/feed", "b@b.com", "link", "html", True)
        db.set_feed_paused(feed2.id, True)

        feeds = db.get_feeds(include_paused=True)
        assert len(feeds) == 2

        feeds = db.get_feeds(include_paused=False)
        assert len(feeds) == 1
        assert feeds[0].url == "https://a.com/feed"

    def test_get_feed_by_id(self, db: Database):
        added = add_feed(db)
        found = db.get_feed(added.id)

        assert found is not None
        assert found.id == added.id
        assert found.url == "https://example.com/feed.xml"

    def test_get_feed_by_url(self, db: Database):
        added = add_feed(db)
        found = db.get_feed("https://example.com/feed.xml")

        assert found is not None
        assert found.id == added.id
        assert found.url == "https://example.com/feed.xml"

    def test_get_feed_not_found(self, db: Database):
        add_feed(db)

        assert db.get_feed("999") is None
        assert db.get_feed("https://notexample.com/feed.xml") is None

    def test_pause(self, db: Database):
        feed = add_feed(db)
        assert feed.paused is False

        db.set_feed_paused(feed.id, True)
        updated = db.get_feed(str(feed.id))

        assert updated is not None
        assert updated.paused is True

    def test_pause_unpause(self, db: Database):
        feed = add_feed(db)
        db.set_feed_paused(feed.id, True)
        db.set_feed_paused(feed.id, False)

        updated = db.get_feed(feed.id)
        assert updated is not None
        assert updated.paused is False

    def test_unpause(self, db: Database):
        feed = add_feed(db)
        db.set_feed_paused(feed.id, False)

        updated = db.get_feed(feed.id)
        assert updated is not None
        assert updated.paused is False

    def test_mark_seen(self, db: Database):
        feed = add_feed(db)

        assert db.is_seen(feed.id, "item-1") is False
        db.mark_seen(feed.id, "item-1")
        assert db.is_seen(feed.id, "item-1") is True
        db.mark_seen(feed.id, "item-1")  # No error
        assert db.is_seen(feed.id, "item-1") is True

    def test_mark_seen_optional(self, db: Database):
        feed = add_feed(db)
        db.mark_seen(feed.id, "item-1", url="https://example.com/post/1")

        cursor = db.connection.execute(
            "SELECT url FROM seen_items WHERE feed_id = ? AND dedup_value = ?",
            (feed.id, "item-1"),
        )
        assert cursor.fetchone()[0] == "https://example.com/post/1"
        db.mark_seen(feed.id, "item-1", url="https://example.com/post/1")  # No error

    def test_is_seen_different_feeds(self, db: Database):
        feed1 = db.add_feed("https://example.com/feed1.xml", "u@e.com", "id", "text", False)
        feed2 = db.add_feed("https://example.com/feed2.xml", "u@e.com", "id", "text", False)

        db.mark_seen(feed1.id, "item-1")

        assert db.is_seen(feed1.id, "item-1") is True
        assert db.is_seen(feed2.id, "item-1") is False

    def test_mark_many_seen(self, db: Database):
        feed = add_feed(db)

        db.mark_many_seen(feed.id, [])  # No error

        cursor = db.connection.execute(
            "SELECT count(*) FROM seen_items WHERE feed_id = ?", (feed.id,)
        )
        assert cursor.fetchone()[0] == 0

        values = ["item-1", "item-2", "item-3"]
        db.mark_many_seen(feed.id, values)

        for val in values:
            assert db.is_seen(feed.id, val) is True

        db.mark_many_seen(feed.id, values)  # No error

    def test_mark_many_seen_optional(self, db: Database):
        feed = add_feed(db)
        values = ["item-1", "item-2"]
        urls = ["https://example.com/1", None]
        db.mark_many_seen(feed.id, values, urls=urls)

        cursor = db.connection.execute(
            "SELECT dedup_value, url FROM seen_items WHERE feed_id = ? ORDER BY dedup_value",
            (feed.id,),
        )
        rows = cursor.fetchall()
        assert rows[0] == ("item-1", "https://example.com/1")
        assert rows[1] == ("item-2", None)

    def test_get_config(self, db: Database):
        assert db.get_config("smtp.host") is None
        db.set_config("smtp.host", "mail.example.com")
        assert db.get_config("smtp.host") == "mail.example.com"
        db.set_config("smtp.host", "new.example.com")
        assert db.get_config("smtp.host") == "new.example.com"

    def test_get_all_config(self, db: Database):
        assert db.get_all_config() == {}

        db.set_config("smtp.host", "mail.example.com")
        db.set_config("smtp.port", "587")
        db.set_config("smtp.user", "user@example.com")

        result = db.get_all_config()
        assert result == {
            "smtp.host": "mail.example.com",
            "smtp.port": "587",
            "smtp.user": "user@example.com",
        }

        db.set_config("smtp.host", "old.example.com")
        db.set_config("smtp.host", "new.example.com")

        result = db.get_all_config()
        assert result == {
            "smtp.host": "new.example.com",
            "smtp.port": "587",
            "smtp.user": "user@example.com",
        }

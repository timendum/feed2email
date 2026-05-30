import sqlite3
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import platformdirs

from feed2email.models import Feed


def _default_db_path() -> Path:
    """Resolve the default database path using platformdirs."""
    data_dir = Path(platformdirs.user_data_dir("feed2email"))
    return data_dir / "feed2email.db"


class Database:
    """SQLite database manager for feed2email."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the Database with a path.

        Args:
            path: Path to the SQLite database file.
            If None, uses the platform default user data directory.
        """
        self.path: Path = path if path is not None else _default_db_path()
        self._lock_conn: sqlite3.Connection | None = None

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")

    def initialize(self) -> None:
        """Create the database schema if it doesn't exist."""
        schema_sql = files("feed2email.db").joinpath("schema.sql").read_text()
        self.connection.executescript(schema_sql)

    def acquire_lock(self) -> bool:
        """Acquire an exclusive lock for single-instance enforcement.

        Returns:
            True if the lock was acquired successfully,
            False if another instance already holds the lock.
        """
        if self._lock_conn is not None:
            return True

        lock_path = self.path.with_suffix(".lock.db")
        try:
            conn = sqlite3.connect(str(lock_path), timeout=0)
            conn.execute("BEGIN EXCLUSIVE")
            self._lock_conn = conn
            return True
        except sqlite3.OperationalError:
            try:
                conn.close()
            except RuntimeError:
                pass
            return False

    def release_lock(self) -> None:
        """Release the exclusive lock held by this instance."""
        if self._lock_conn is None:
            return
        try:
            self._lock_conn.rollback()
        except sqlite3.Error:
            pass
        finally:
            try:
                self._lock_conn.close()
            except sqlite3.Error:
                pass
            self._lock_conn = None

    def close(self) -> None:
        """Close all database connections and release locks."""
        self.release_lock()
        if self.connection is None:
            return
        try:
            self.connection.close()
        except sqlite3.Error:
            pass

    def is_seen(self, feed_id: int, dedup_value: str) -> bool:
        """Check if an item has already been seen for a given feed.

        Args:
            feed_id: The feed's ID.
            dedup_value: The key value to check.

        Returns:
            True if the item has been seen, False otherwise.
        """
        cursor = self.connection.execute(
            "SELECT id FROM seen_items WHERE feed_id = ? AND dedup_value = ?",
            (feed_id, dedup_value),
        )
        return cursor.fetchone() is not None

    def mark_seen(self, feed_id: int, dedup_value: str, url: str | None = None) -> None:
        """Record a single item as seen for a given feed.

        Args:
            feed_id: The feed's ID.
            dedup_value: The key value to record.
            url: Optional URL of the feed item.
        """
        self.connection.execute(
            "INSERT OR IGNORE INTO seen_items (feed_id, dedup_value, url) VALUES (?, ?, ?)",
            (feed_id, dedup_value, url),
        )
        self.connection.commit()

    def mark_many_seen(
        self, feed_id: int, values: list[str], urls: list[str | None] | None = None
    ) -> None:
        """Record multiple items as seen for a given feed in a single transaction.

        Args:
            feed_id: The feed's ID.
            values: List of key values to record.
            urls: Optional list of URLs corresponding to each value.
                  Must be the same length as values if provided.
        """
        if not values:
            return

        if urls is None:
            urls = [None] * len(values)

        rows = [(feed_id, val, url) for val, url in zip(values, urls, strict=True)]
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_items (feed_id, dedup_value, url) VALUES (?, ?, ?)",
            rows,
        )
        self.connection.commit()

    def get_config(self, key: str) -> str | None:
        """Get a configuration value by key.

        Args:
            key: The configuration key to look up.

        Returns:
            The value as a string, or None if the key is not set.
        """
        cursor = self.connection.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row is not None else None

    def set_config(self, key: str, value: str) -> None:
        """Set or update a configuration value.

        Args:
            key: The configuration key.
            value: The value to store.
        """
        self.connection.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.connection.commit()

    def delete_config(self, key: str) -> bool:
        """Delete a configuration value by key.

        Args:
            key: The configuration key to delete.

        Returns:
            True if the key was found and deleted, False if not found.
        """
        cursor = self.connection.execute("DELETE FROM config WHERE key = ?", (key,))
        self.connection.commit()
        return cursor.rowcount > 0

    def get_all_config(self) -> dict[str, str]:
        """Get all configuration key-value pairs.

        Returns:
            A dictionary mapping config keys to their values.
        """
        cursor = self.connection.execute("SELECT key, value FROM config")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _row_to_feed(self, row: tuple) -> Feed:
        """Convert a database row tuple to a Feed dataclass."""
        return Feed(
            id=row[0],
            url=row[1],
            recipient=row[2],
            dedup_key=row[3],
            format=row[4],
            item_date=bool(row[5]),
            paused=bool(row[6]),
            created_at=datetime.fromisoformat(row[7]),
        )

    def add_feed(
        self,
        url: str,
        recipient: str | None,
        dedup_key: str,
        format: str,
        item_date: bool,
    ) -> Feed:
        """Add a new feed to the database.

        Args:
            url: The feed URL.
            recipient: The recipient email address, or None to use default-recipient.
            dedup_key: Key to use ('id', 'link', or 'title').
            format: Email format ('text' or 'html').
            item_date: Whether to use item publication date for email Date header.

        Returns:
            The newly created Feed object.
        """
        cursor = self.connection.execute(
            "INSERT INTO feeds (url, recipient, dedup_key, format, item_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, recipient, dedup_key, format, int(item_date)),
        )
        self.connection.commit()

        # Fetch the newly inserted feed to get all default values
        row = self.connection.execute(
            "SELECT id, url, recipient, dedup_key, format, item_date, paused, created_at "
            "FROM feeds WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

        return self._row_to_feed(row)

    def remove_feed(self, feed_ref: str | int) -> bool:
        """Remove a feed and its associated seen items from the database.

        Args:
            feed_ref: A feed URL or Feed_ID (as a string).

        Returns:
            True if the feed was found and removed, False if not found.
        """
        feed = self.get_feed(feed_ref)
        if feed is None:
            return False

        # Foreing keys and CASCADE to delete childs
        self.connection.execute("DELETE FROM feeds WHERE id = ?", (feed.id,))
        self.connection.commit()
        return True

    def get_feeds(self, include_paused: bool = True) -> list[Feed]:
        """Retrieve all feeds from the database.

        Args:
            include_paused: If True, include paused feeds.

        Returns:
            List of Feed objects.
        """
        query = (
            "SELECT id, url, recipient, dedup_key, format, item_date, paused, created_at "
            "FROM feeds " + ("" if include_paused else "WHERE paused = 0 ") + "ORDER BY id"
        )
        cursor = self.connection.execute(query)

        return [self._row_to_feed(row) for row in cursor.fetchall()]

    def get_feed(self, feed_ref: str | int) -> Feed | None:
        """Retrieve a single feed by URL or Feed_ID.

        Args:
            feed_ref: A feed URL or Feed_ID.

        Returns:
            The Feed object if found, None otherwise.
        """

        # Case: Feed_ID
        try:
            feed_id = int(feed_ref)
            row = self.connection.execute(
                "SELECT id, url, recipient, dedup_key, format, item_date, paused, created_at "
                "FROM feeds WHERE id = ?",
                (feed_id,),
            ).fetchone()
            if row is not None:
                return self._row_to_feed(row)
        except ValueError:
            pass

        # Fall back to URL
        row = self.connection.execute(
            "SELECT id, url, recipient, dedup_key, format, item_date, paused, created_at "
            "FROM feeds WHERE url = ?",
            (feed_ref,),
        ).fetchone()
        if row is not None:
            return self._row_to_feed(row)

        return None

    def set_feed_paused(self, feed_id: int, paused: bool) -> None:
        """Set the paused status of a feed.

        Args:
            feed_id: The numeric ID of the feed.
            paused: True to pause the feed, False to unpause.
        """
        conn = self.connection
        conn.execute(
            "UPDATE feeds SET paused = ? WHERE id = ?",
            (int(paused), feed_id),
        )
        conn.commit()

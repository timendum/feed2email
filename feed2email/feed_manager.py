import logging

from feed2email.db import Database
from feed2email.feed_fetcher import FeedFetcher
from feed2email.models import Feed, FeedItem, validate_email, validate_url

logger = logging.getLogger(__name__)


class FeedError(Exception):
    """Raised when a feed operation fails."""


class FeedManager:
    """Manages feed lifecycle operations: add, remove, list, pause, unpause."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._fetcher = FeedFetcher.from_db(db)

    def add_feed(
        self,
        url: str,
        recipient: str | None = None,
        dedup_key: str = "link",
        format: str = "html",
        item_date: bool = False,
        mark_read: bool = False,
    ) -> Feed:
        """Add a new feed to the database.

        Always fetches the feed to validate it is reachable and parseable.
        Marks all items except the most recent one as read.

        Args:
            url: The feed URL.
            recipient: Email address. None = use default-recipient at run time.
            dedup_key: Deduplication key field.
            format: Email format ('text' or 'html').
            item_date: Use item publication date for email Date header?
            mark_read: Mark *all* current items as seen (including the latest)?

        Returns:
            Feed object.

        Raises:
            FeedError: If the URL is invalid, the feed already exists, or the
                feed cannot be fetched/parsed.
        """
        if not validate_url(url):
            raise FeedError(f"Invalid URL: {url}")

        if recipient is not None and not validate_email(recipient):
            raise FeedError(f"Invalid email address: {recipient}")

        existing = self._db.get_feed(url)
        if existing is not None:
            raise FeedError(f"Feed already exists: {url}")

        # Always fetch the feed to validate it is reachable and parseable.
        result = self._fetcher.fetch(url)
        if not result.success:
            raise FeedError(f"Failed to fetch feed: {result.error}")

        feed = self._db.add_feed(
            url=url,
            recipient=recipient,
            dedup_key=dedup_key,
            format=format,
            item_date=item_date,
        )

        # Mark items as seen based on the mark_read flag:
        # - mark_read=True  → mark ALL items as read
        # - mark_read=False → mark all EXCEPT the latest item as read
        self._mark_items_on_add(feed, result.items, mark_read=mark_read)

        return feed

    def remove_feed(self, feed_ref: str | int) -> None:
        """Remove a feed from the database.

        Args:
            feed_ref: Feed URL or Feed_ID.

        Raises FeedError if the feed is not found.
        """
        removed = self._db.remove_feed(feed_ref)
        if not removed:
            raise FeedError(f"Feed not found: {feed_ref}")

    def list_feeds(self) -> list[Feed]:
        """Returns list of Feed."""
        return self._db.get_feeds(include_paused=True)

    def pause_feed(self, feed_ref: str | int) -> str:
        """Pause a feed by Feed URL or Feed_ID.

        Returns:
            A message indicating the result.

        Raises FeedError if the feed is not found.
        """
        feed = self._db.get_feed(feed_ref)
        if feed is None:
            raise FeedError(f"Feed not found: {feed_ref}")

        if feed.paused:
            return f"Feed is already paused: {feed.url}"

        self._db.set_feed_paused(feed.id, paused=True)
        return f"Feed paused: {feed.url}"

    def unpause_feed(self, feed_ref: str | int) -> str:
        """Unpause a feed by Feed URL or Feed_ID.

        Returns:
            A message indicating the result.

        Raises FeedError if the feed is not found.
        """
        feed = self._db.get_feed(feed_ref)
        if feed is None:
            raise FeedError(f"Feed not found: {feed_ref}")

        if not feed.paused:
            return f"Feed is already active: {feed.url}"

        self._db.set_feed_paused(feed.id, paused=False)
        return f"Feed unpaused: {feed.url}"

    def resolve_recipient(self, feed: Feed) -> str:
        """Get the recipient, feed specific or default.

        Args:
            feed: The feed to resolve the recipient for.

        Returns:
            The resolved recipient email address.
        """
        if feed.recipient is not None:
            return feed.recipient

        default_recipient = self._db.get_config("default-recipient")
        if default_recipient is None:
            raise FeedError(
                f"No recipient for feed {feed.url} and no default-recipient configured. "
                "Set a default with: feed2email config default-recipient <email>"
            )
        return default_recipient

    def _mark_items_on_add(self, feed: Feed, items: list[FeedItem], mark_read: bool) -> None:
        """Mark items as seen when adding a feed.

        Args:
            feed: The newly added feed.
            items: The items fetched from the feed.
            mark_read: If True, mark ALL items as seen. If False, mark all
                items except the most recent one (first in the list) as seen.
        """
        if not items:
            return

        if all(item.published for item in items):
            items = sorted(items, key=lambda item: item.published, reverse=True)
        items_to_mark = items if mark_read else items[1:]

        if not items_to_mark:
            return

        dedup_values: list[str] = []
        urls: list[str | None] = []

        for item in items_to_mark:
            value = self._get_dedup_value(item, feed.dedup_key)
            if value is None:
                logger.warning(
                    "Skipping item missing '%s' field during mark-read for %s",
                    feed.dedup_key,
                    feed.url,
                )
                continue
            dedup_values.append(value)
            urls.append(item.link)

        if dedup_values:
            self._db.mark_many_seen(feed.id, dedup_values, urls)

    def edit_feed(
        self,
        feed_ref: str | int,
        url: str | None = None,
        format: str | None = None,
        item_date: bool | None = None,
    ) -> Feed:
        """Edit properties of an existing feed.

        Args:
            feed_ref: Feed URL or Feed_ID identifying the feed to edit.
            url: New feed URL (validated for format and reachability).
            format: New email format ('text' or 'html').
            item_date: Whether to use item publication date for email Date header.

        Returns:
            The updated Feed object.

        Raises:
            FeedError: If the feed is not found, validation fails, or the new
                URL is unreachable.
        """
        if url is None and format is None and item_date is None:
            raise FeedError("Nothing to update. Specify at least one option to change.")

        feed = self._db.get_feed(feed_ref)
        if feed is None:
            raise FeedError(f"Feed not found: {feed_ref}")

        if url is not None:
            if not validate_url(url):
                raise FeedError(f"Invalid URL: {url}")

            # Check for duplicates (skip if unchanged)
            if url != feed.url:
                existing = self._db.get_feed(url)
                if existing is not None:
                    raise FeedError(f"Feed already exists with that URL: {url}")

                # Validate the new URL is reachable
                result = self._fetcher.fetch(url)
                if not result.success:
                    raise FeedError(f"Failed to fetch feed at new URL: {result.error}")

        return self._db.update_feed(
            feed.id,
            url=url,
            format=format,
            item_date=item_date,
        )

    @staticmethod
    def _get_dedup_value(item: FeedItem, dedup_key: str) -> str | None:
        """Extract the deduplication value from a feed item.

        Args:
            item: A FeedItem instance.
            dedup_key: The field to use ('id', 'link', or 'title').

        Returns:
            The field value as a string, or None if the field is missing/empty.
        """
        if dedup_key == "id":
            return item.id if item.id else None
        elif dedup_key == "link":
            return item.link if item.link else None
        elif dedup_key == "title":
            return item.title.lower().strip() if item.title else None
        return None

import logging

from feed2email.db import Database
from feed2email.feed_fetcher import DEFAULT_USER_AGENT, FeedFetcher
from feed2email.models import Feed, validate_email, validate_url

logger = logging.getLogger(__name__)


class FeedError(Exception):
    """Raised when a feed operation fails."""


class FeedManager:
    """Manages feed lifecycle operations: add, remove, list, pause, unpause."""

    def __init__(self, db: Database) -> None:
        self._db = db
        user_agent = db.get_config("user-agent") or DEFAULT_USER_AGENT
        self._fetcher = FeedFetcher(user_agent=user_agent)

    def add_feed(
        self,
        url: str,
        recipient: str | None = None,
        dedup_key: str = "id",
        format: str = "text",
        item_date: bool = False,
        mark_read: bool = False,
    ) -> Feed:
        """Add a new feed to the database.

        Args:
            url: The feed URL.
            recipient: Email address. None = use default-recipient at run time.
            dedup_key: Deduplication key field ('id', 'link', or 'title').
            format: Email format ('text' or 'html').
            item_date: Use item publication date for email Date header?
            mark_read: Mark all current items as seen?

        Returns:
            Feed object.
        """
        if not validate_url(url):
            raise FeedError(f"Invalid URL: {url}")

        if recipient is not None and not validate_email(recipient):
            raise FeedError(f"Invalid email address: {recipient}")

        if recipient is None and self._db.get_config("default-recipient") is None:
            raise FeedError(
                "No recipient specified and no default-recipient configured. "
                "Set a default with: feed2email config default-recipient <email>"
            )

        existing = self._db.get_feed(url)
        if existing is not None:
            raise FeedError(f"Feed already exists: {url}")

        feed = self._db.add_feed(
            url=url,
            recipient=recipient,
            dedup_key=dedup_key,
            format=format,
            item_date=item_date,
        )

        if mark_read:
            self._mark_existing_items_read(feed)

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

    def _mark_existing_items_read(self, feed: Feed) -> None:
        """Fetch the feed and mark all current items as seen.

        Args:
            feed: The feed to mark items as read for.
        """
        result = self._fetcher.fetch(feed.url)

        if not result.success:
            logger.warning(
                "Could not mark existing items as read for %s: %s",
                feed.url,
                result.error,
            )
            return

        dedup_values: list[str] = []
        urls: list[str | None] = []

        for item in result.items:
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

    @staticmethod
    def _get_dedup_value(item, dedup_key: str) -> str | None:
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
            return item.title if item.title else None
        return None

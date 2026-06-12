"""Runner module: orchestrates the full feed2email run cycle."""

import logging
from datetime import UTC, datetime

from feed2email.db import Database
from feed2email.email_sender import EmailSender
from feed2email.feed_fetcher import FeedFetcher
from feed2email.models import EmailMessage, Feed, FeedItem, RunResult
from feed2email.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class Runner:
    """Orchestrates the full run cycle: fetch → deduplicate → render → send → mark seen."""

    def __init__(
        self,
        db: Database,
        fetcher: FeedFetcher,
        mailer: EmailSender | None,
        renderer: TemplateRenderer,
    ) -> None:
        self._db = db
        self._fetcher = fetcher
        self._mailer = mailer
        self._renderer = renderer

    def run(self, dry_run: bool = False) -> RunResult:
        """Execute the full run cycle.

        Args:
            dry_run: If True, display items without sending or recording.

        Returns:
            RunResult with counts and implicit exit code.
        """
        result = RunResult()

        if not self._db.acquire_lock():
            logger.error("Another instance is already running")
            result.feeds_failed = 1
            return result

        try:
            feeds = self._db.get_feeds(include_paused=False)

            if not feeds:
                return result

            user_agent = self._db.get_config("user-agent") or "feed2email"

            for feed in feeds:
                self._process_feed(feed, dry_run, user_agent, result)
        finally:
            self._db.release_lock()

        return result

    def _process_feed(
        self,
        feed: Feed,
        dry_run: bool,
        user_agent: str,
        result: RunResult,
    ) -> None:
        """Process a single feed: fetch, deduplicate, render, send."""
        # Resolve recipient
        recipient = self._resolve_recipient(feed)
        if recipient is None:
            logger.warning(
                "Skipping feed %s: no recipient configured and no default-recipient set",
                feed.url,
            )
            result.feeds_failed += 1
            return

        # Fetch feed
        fetch_result = self._fetcher.fetch(feed.url)
        if not fetch_result.success:
            logger.warning("Failed to fetch feed %s: %s", feed.url, fetch_result.error)
            result.feeds_failed += 1
            return

        result.feeds_processed += 1

        # Process each item
        for item in fetch_result.items:
            self._process_item(
                item=item,
                feed=feed,
                recipient=recipient,
                feed_title=fetch_result.feed_title,
                user_agent=user_agent,
                dry_run=dry_run,
                result=result,
            )

    def _process_item(
        self,
        item: FeedItem,
        feed: Feed,
        recipient: str,
        feed_title: str,
        user_agent: str,
        dry_run: bool,
        result: RunResult,
    ) -> None:
        """Process a single feed item: deduplicate, render, send, mark seen."""
        # Extract dedup value
        dedup_value = self._get_dedup_value(item, feed.dedup_key)
        if dedup_value is None:
            logger.warning(
                "Skipping item missing '%s' field in feed %s",
                feed.dedup_key,
                feed.url,
            )
            return

        # Check if already seen
        if self._db.is_seen(feed.id, dedup_value):
            return

        # Compute subject
        subject = self._renderer.make_subject(item, feed, feed_title)

        if dry_run:
            # Display one line per item: recipient, subject, feed URL
            print(f"{recipient} | {subject} | {feed.url}")
            result.items_sent += 1
            return

        # Render email body
        body = self._renderer.render_body(item, feed, feed_title, feed.format)

        # Compute date header
        date = self._compute_date(item, feed)

        # Determine content type
        content_type = "text/html" if feed.format == "html" else "text/plain"

        # Build email message
        message = EmailMessage(
            recipient=recipient,
            subject=subject,
            body=body,
            content_type=content_type,
            date=date,
            feed_id=feed.url,
            item_url=item.link,
            item_id=item.id,
            user_agent=user_agent,
        )

        # Send email
        if self._mailer is None:
            logger.error("No mailer configured for non-dry-run mode")
            result.items_failed += 1
            return

        send_result = self._mailer.send(message)
        if not send_result.success:
            logger.error(
                "Failed to send email for item in feed %s: %s",
                feed.url,
                send_result.error,
            )
            result.items_failed += 1
            return

        result.items_sent += 1

        # Mark as seen
        try:
            self._db.mark_seen(feed.id, dedup_value, item.link)
        except RuntimeError:
            logger.warning(
                "Failed to mark item as seen in feed %s (may be re-sent next run)",
                feed.url,
            )

    def _resolve_recipient(self, feed: Feed) -> str | None:
        """Resolve the recipient for a feed."""
        if feed.recipient is not None:
            return feed.recipient
        return self._db.get_config("default-recipient")

    def _compute_date(self, item: FeedItem, feed: Feed) -> datetime:
        """Compute the Date header value."""
        now = datetime.now(tz=UTC)

        if not feed.item_date:
            return now

        if item.published is None:
            logger.warning(
                "Item in feed %s has no publication date; using current time",
                feed.url,
            )
            return now

        # Ensure the date is timezone-aware
        if item.published.tzinfo is None:
            return item.published.replace(tzinfo=UTC)

        return item.published

    @staticmethod
    def _get_dedup_value(item: FeedItem, dedup_key: str) -> str | None:
        """Extract the key value from a feed item.

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

    def compute_exit_code(self, result: RunResult) -> int:
        """Compute the exit code from a RunResult.

        Returns:
            0: Success (or no work to do)
            1: Partial failure (some feeds/emails failed, some succeeded)
            2: Total failure (all feeds failed or no items processed)
        """
        has_failures = result.feeds_failed > 0 or result.items_failed > 0
        has_successes = result.items_sent > 0 or (
            result.feeds_processed > 0 and result.items_failed == 0 and result.items_sent == 0
        )

        if not has_failures:
            return 0

        if has_successes:
            return 1

        return 2

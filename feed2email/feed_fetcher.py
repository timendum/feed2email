import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import feedendum
import requests
from feedendum.exceptions import FeedParseError, FeedXMLError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from feed2email.models import FeedItem, FetchResult

if TYPE_CHECKING:
    from feed2email.db import Database

DEFAULT_USER_AGENT = "feed2email"

logger = logging.getLogger(__name__)


class FeedFetcher:
    """Fetches and parses feeds."""

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
        retry_max: int = 0,
        retry_backoff: float = 0.5,
        host_delay: float = 0,
    ):
        self._timeout = timeout
        self._host_delay = host_delay
        self._last_fetch_by_host: dict[str, float] = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

        if retry_max > 0:
            retry = Retry(
                total=retry_max,
                backoff_factor=retry_backoff,
                status_forcelist=[403, 429, 500, 502, 503, 504],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

    @classmethod
    def from_db(cls, db: "Database") -> "FeedFetcher":
        return cls(
            user_agent=db.get_config("user-agent") or DEFAULT_USER_AGENT,
            retry_max=int(db.get_config("retry.max") or 0),
            retry_backoff=float(db.get_config("retry.backoff") or 0.5),
            host_delay=float(db.get_config("host-delay") or 0),
        )

    def fetch(self, url: str) -> FetchResult:
        """Fetch a feed from the given URL and return parsed items."""
        logger.debug("Fetching feed: %s", url)
        self._wait_for_host(url)

        try:
            text = self._download(url)
        except (RuntimeError, requests.RequestException) as e:
            logger.info("Fetch failed for %s: %s", url, e)
            return FetchResult(
                success=False,
                items=[],
                feed_title="",
                error=f"Failed to fetch {url}: {e}",
            )
        finally:
            self._record_fetch(url)

        try:
            feed = self._parse(text)
        except RuntimeError as e:
            return FetchResult(
                success=False,
                items=[],
                feed_title="",
                error=f"Failed to parse feed from {url}: {e}",
            )

        items = [self._convert_item(item) for item in feed.items]
        feed_title = feed.title or ""
        logger.info("Fetched %d items from %s", len(items), url)

        return FetchResult(
            success=True,
            items=items,
            feed_title=feed_title,
        )

    def _download(self, url: str) -> str:
        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def _wait_for_host(self, url: str) -> None:
        """Sleep if the same host was fetched recently and host_delay is configured."""
        if self._host_delay <= 0:
            return
        host = self._get_host(url)
        if host in self._last_fetch_by_host:
            elapsed = time.monotonic() - self._last_fetch_by_host[host]
            remaining = self._host_delay - elapsed
            if remaining > 0:
                logger.info(
                    "Waiting %.1fs before fetching %s (same host: %s)",
                    remaining,
                    url,
                    host,
                )
                time.sleep(remaining)

    def _record_fetch(self, url: str) -> None:
        if self._host_delay <= 0:
            return
        host = self._get_host(url)
        self._last_fetch_by_host[host] = time.monotonic()

    @staticmethod
    def _get_host(url: str) -> str:
        parsed = urlparse(url)
        return parsed.hostname or parsed.netloc

    def _parse(self, text: str) -> feedendum.Feed:
        parsers = [
            feedendum.from_rss_text,
            feedendum.from_atom_text,
            feedendum.from_rdf_text,
        ]
        for parser in parsers:
            try:
                return parser(text)
            except (FeedParseError, FeedXMLError):
                continue
        raise ValueError("Unable to parse feed")

    def _convert_item(self, item: feedendum.FeedItem) -> FeedItem:
        return FeedItem(
            id=item.id,
            title=item.title,
            link=item.url,
            content=item.content,
            published=item.update,
        )

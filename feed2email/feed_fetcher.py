import feedendum
import requests
from feedendum.exceptions import FeedParseError, FeedXMLError

from feed2email.models import FeedItem, FetchResult

DEFAULT_USER_AGENT = "feed2email"


class FeedFetcher:
    """Fetches and parses feeds."""

    def __init__(self, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch(self, url: str) -> FetchResult:
        """Fetch a feed from the given URL and return parsed items.

        Returns a FetchResult.
        """
        try:
            text = self._download(url)
        except RuntimeError as e:
            return FetchResult(
                success=False,
                items=[],
                feed_title="",
                error=f"Failed to fetch {url}: {e}",
            )

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

    def _parse(self, text: str) -> feedendum.Feed:
        parsers = [
            feedendum.from_rss_text,
            feedendum.from_atom_text,
            feedendum.from_rdf_text,
        ]
        last_error: Exception | None = None
        for parser in parsers:
            try:
                return parser(text)
            except (FeedParseError, FeedXMLError) as e:
                last_error = e
                continue
        raise last_error or ValueError("Unable to parse feed")

    def _convert_item(self, item: feedendum.FeedItem) -> FeedItem:
        return FeedItem(
            id=item.id,
            title=item.title,
            link=item.url,
            content=item.content,
            published=item.published,
        )

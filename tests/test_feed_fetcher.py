"""Unit tests for FeedFetcher."""

from unittest.mock import patch, MagicMock

from feed2email.feed_fetcher import DEFAULT_USER_AGENT, FeedFetcher


class TestFeedFetcherUserAgent:
    """Tests for custom User-Agent support in FeedFetcher."""

    def test_default_user_agent(self):
        fetcher = FeedFetcher()
        assert fetcher._session.headers["User-Agent"] == DEFAULT_USER_AGENT

    def test_custom_user_agent(self):
        fetcher = FeedFetcher(user_agent="MyBot/1.0")
        assert fetcher._session.headers["User-Agent"] == "MyBot/1.0"

    def test_custom_user_agent_sent_in_request(self):
        fetcher = FeedFetcher(user_agent="CustomAgent/2.0")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<rss></rss>"
        mock_response.apparent_encoding = "utf-8"
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher._session, "get", return_value=mock_response) as mock_get:
            fetcher.fetch("https://example.com/feed.xml")
            mock_get.assert_called_once_with("https://example.com/feed.xml", timeout=30)
            # The session has the custom user agent set in headers
            assert fetcher._session.headers["User-Agent"] == "CustomAgent/2.0"

"""Unit tests for FeedFetcher."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TypedDict
from unittest.mock import MagicMock, patch

import pytest

from feed2email.feed_fetcher import DEFAULT_USER_AGENT, FeedFetcher


class _HandlerState(TypedDict):
    responses: list[tuple[int, str]]
    request_count: int


SAMPLE_RSS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0"><channel><title>Test</title>'
    "<item><title>Hello</title><link>http://example.com/1</link></item>"
    "</channel></rss>"
)


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
        mock_response.text = "<rss version='2.0'><channel></channel></rss>"
        mock_response.apparent_encoding = "utf-8"
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher._session, "get", return_value=mock_response) as mock_get:
            fetcher.fetch("https://example.com/feed.xml")
            mock_get.assert_called_once_with("https://example.com/feed.xml", timeout=30)
            # The session has the custom user agent set in headers
            assert fetcher._session.headers["User-Agent"] == "CustomAgent/2.0"


class TestFeedFetcherRetry:
    @pytest.fixture
    def http_server(self):
        handler_state: _HandlerState = {
            "responses": [],
            "request_count": 0,
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                handler_state["request_count"] += 1
                if handler_state["responses"]:
                    status, body = handler_state["responses"].pop(0)
                else:
                    status, body = 200, SAMPLE_RSS
                self.send_response(status)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, format, *args):
                pass  # suppress logs during tests

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}", handler_state

        server.shutdown()

    def test_no_retry_by_default(self, http_server):
        url, state = http_server
        state["responses"] = [(503, "Service Unavailable")]

        fetcher = FeedFetcher(retry_max=0)
        result = fetcher.fetch(url + "/feed.xml")

        assert not result.success
        assert state["request_count"] == 1

    def test_retry_and_stop(self, http_server):
        url, state = http_server
        state["responses"] = [(503, "Service Unavailable"), (404, "Not Found")]

        fetcher = FeedFetcher(retry_max=2, retry_backoff=0)
        result = fetcher.fetch(url + "/feed.xml")

        assert not result.success
        assert state["request_count"] == 2

    def test_retry_exhausted(self, http_server):
        url, state = http_server
        state["responses"] = [
            (502, "Bad Gateway"),
            (429, "Bad Gateway"),
            (502, "Bad Gateway"),
        ]

        fetcher = FeedFetcher(retry_max=2, retry_backoff=0)
        result = fetcher.fetch(url + "/feed.xml")

        assert not result.success
        assert state["request_count"] == 3

    def test_retry_with_backoff_factor(self, http_server):
        url, state = http_server
        state["responses"] = [(500, "Internal Server Error")]

        fetcher = FeedFetcher(retry_max=1, retry_backoff=0.01)
        result = fetcher.fetch(url + "/feed.xml")

        assert result.success
        assert state["request_count"] == 2


class TestFeedFetcherHostDelay:
    def test_host_delay_sleeps_between_same_host_fetches(self):
        fetcher = FeedFetcher(host_delay=2.0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_RSS
        mock_response.apparent_encoding = "utf-8"
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(fetcher._session, "get", return_value=mock_response),
            patch("feed2email.feed_fetcher.time.sleep") as mock_sleep,
        ):
            fetcher.fetch("https://example.com/feed1.xml")
            fetcher.fetch("https://example.com/feed2.xml")

            # Should have slept once for the second request to the same host
            assert mock_sleep.call_count == 1
            delay = mock_sleep.call_args[0][0]
            assert delay > 0
            assert delay <= 2.0

"""Unit tests for the TemplateRenderer."""

from datetime import datetime, timezone

import pytest

from feed2email.models import FeedItem
from feed2email.template_renderer import TemplateRenderer


@pytest.fixture
def renderer() -> TemplateRenderer:
    return TemplateRenderer()


class TestMakeSubject:
    """Tests for make_subject() fallback chain and truncation."""

    def test_uses_title_when_present(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="My Article", link="http://example.com",
            content=None, published=None,
        )
        assert renderer.make_subject(item) == "My Article"

    def test_truncates_title_to_255_chars(self, renderer: TemplateRenderer) -> None:
        long_title = "A" * 300
        item = FeedItem(
            id="1", title=long_title, link="http://example.com",
            content=None, published=None,
        )
        subject = renderer.make_subject(item)
        assert len(subject) == 255
        assert subject == "A" * 255

    def test_falls_back_to_link_when_no_title(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title=None, link="http://example.com/article",
            content=None, published=None,
        )
        assert renderer.make_subject(item) == "http://example.com/article"

    def test_falls_back_to_no_title_when_no_title_or_link(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title=None, link=None,
            content=None, published=None,
        )
        assert renderer.make_subject(item) == "No Title"

    def test_empty_title_falls_back_to_link(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="", link="http://example.com",
            content=None, published=None,
        )
        assert renderer.make_subject(item) == "http://example.com"

    def test_empty_title_and_empty_link_falls_back_to_no_title(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="", link="",
            content=None, published=None,
        )
        assert renderer.make_subject(item) == "No Title"


class TestStripHtml:
    """Tests for strip_html() static method."""

    def test_removes_simple_tags(self) -> None:
        assert TemplateRenderer.strip_html("<p>Hello</p>") == "Hello"

    def test_removes_nested_tags(self) -> None:
        assert TemplateRenderer.strip_html("<div><p>Hello</p></div>") == "Hello"

    def test_removes_tags_with_attributes(self) -> None:
        html = '<a href="http://example.com" class="link">Click here</a>'
        assert TemplateRenderer.strip_html(html) == "Click here"

    def test_preserves_text_between_tags(self) -> None:
        html = "<p>First</p> <p>Second</p>"
        assert TemplateRenderer.strip_html(html) == "First Second"

    def test_handles_self_closing_tags(self) -> None:
        html = "Hello<br/>World"
        assert TemplateRenderer.strip_html(html) == "HelloWorld"

    def test_handles_empty_string(self) -> None:
        assert TemplateRenderer.strip_html("") == ""

    def test_handles_no_tags(self) -> None:
        assert TemplateRenderer.strip_html("Just plain text") == "Just plain text"

    def test_handles_void_elements(self) -> None:
        html = "Line1<br>Line2"
        assert TemplateRenderer.strip_html(html) == "Line1Line2"


class TestRender:
    """Tests for render() method."""

    def test_renders_plain_text_with_all_fields(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Test Title", link="http://example.com/article",
            content="Article body text",
            published=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        result = renderer.render(item, "My Feed", "http://example.com/feed", "text")
        assert "Test Title" in result
        assert "http://example.com/article" in result
        assert "Article body text" in result
        assert "My Feed" in result
        assert "http://example.com/feed" in result
        assert "2024-01-15 10:30:00" in result

    def test_renders_html_with_all_fields(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Test Title", link="http://example.com/article",
            content="Article body text",
            published=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        result = renderer.render(item, "My Feed", "http://example.com/feed", "html")
        assert "Test Title" in result
        assert "http://example.com/article" in result
        assert "Article body text" in result
        assert "My Feed" in result
        assert "http://example.com/feed" in result
        assert "2024-01-15 10:30:00" in result
        assert "<html>" in result

    def test_body_uses_content(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Title", link=None,
            content="Content body",
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "text")
        assert "Content body" in result

    def test_body_uses_empty_string_when_no_content(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Title", link=None,
            content=None,
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "text")
        # Should still render without error
        assert "Title" in result

    def test_plain_text_strips_html_from_body(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Title", link=None,
            content="<p>Hello <b>World</b></p>",
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "text")
        assert "Hello World" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_html_format_preserves_html_in_body(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Title", link=None,
            content="<p>Hello <b>World</b></p>",
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "html")
        assert "<p>Hello <b>World</b></p>" in result

    def test_date_is_empty_string_when_published_is_none(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title="Title", link=None,
            content="Body",
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "text")
        # Date line should end with empty value (no date formatted)
        assert "Date: " in result
        # Verify no date string is present
        assert "2024" not in result

    def test_missing_title_renders_empty(self, renderer: TemplateRenderer) -> None:
        item = FeedItem(
            id="1", title=None, link="http://example.com",
            content="Body",
            published=None,
        )
        result = renderer.render(item, "Feed", "http://feed.url", "text")
        assert "http://example.com" in result

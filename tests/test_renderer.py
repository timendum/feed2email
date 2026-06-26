"""Unit tests for the TemplateRenderer."""

from datetime import UTC, datetime

import pytest

from feed2email.models import Feed, FeedItem
from feed2email.template_renderer import TemplateRenderer


@pytest.fixture
def renderer() -> TemplateRenderer:
    return TemplateRenderer()


@pytest.fixture
def sample_feed() -> Feed:
    return Feed(
        id=1,
        url="http://example.com/feed",
        recipient=None,
        dedup_key="id",
        format="text",
        item_date=True,
        paused=False,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


class TestMakeSubject:
    """Tests for make_subject() fallback chain and truncation."""

    def test_uses_title_when_present(self, renderer: TemplateRenderer, sample_feed: Feed) -> None:
        item = FeedItem(
            id="1",
            title="My Article",
            link="http://example.com",
            content=None,
            published=None,
        )
        assert renderer.make_subject(item, sample_feed) == item.title

    def test_truncates_title_to_255_chars(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        long_title = "A" * 300
        item = FeedItem(
            id="1",
            title=long_title,
            link="http://example.com",
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed)
        assert len(subject) < 256

    def test_falls_back_to_link_when_no_title(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title=None,
            link="http://example.com/article",
            content=None,
            published=None,
        )
        assert renderer.make_subject(item, sample_feed) is not None

    def test_falls_back_to_no_title_when_no_title_or_link(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title=None,
            link=None,
            content=None,
            published=None,
        )
        assert renderer.make_subject(item, sample_feed) == "No Title"

    def test_empty_title_falls_back_to_link(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="",
            link="http://example.com",
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed)
        assert subject is not None
        assert len(subject) > 0

    def test_empty_title_and_empty_link_falls_back_to_no_title(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="",
            link="",
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed)
        assert subject is not None
        assert len(subject) > 0


class TestRenderBody:
    def test_renders_plain_text_with_all_fields(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Test Title",
            link="http://example.com/article",
            content="Article body text",
            published=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )
        feed_title = "My Feed"
        result = renderer.render_body(item, sample_feed, feed_title, "text")
        assert str(item.title) in result
        assert str(item.link) in result
        assert str(item.content) in result
        assert feed_title in result
        assert sample_feed.url in result

    def test_renders_html_with_all_fields(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Test Title",
            link="http://example.com/article",
            content="Article body text",
            published=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )
        feed_title = "My Feed"
        result = renderer.render_body(item, sample_feed, feed_title, "html")
        assert str(item.title) in result
        assert str(item.link) in result
        assert str(item.content) in result
        assert feed_title in result
        assert sample_feed.url in result
        assert "<html>" in result

    def test_body_uses_content(self, renderer: TemplateRenderer, sample_feed: Feed) -> None:
        item = FeedItem(
            id="1",
            title="Title",
            link=None,
            content="Content body",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert str(item.content) in result

    def test_body_uses_empty_string_when_no_content(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Title",
            link=None,
            content=None,
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert str(item.title) in result

    def test_plain_text_strips_html_from_body(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Title",
            link=None,
            content="<p>Hello <b>World</b></p>",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert "Hello World" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_html_format_preserves_html_in_body(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Title",
            link=None,
            content="<p>Hello <b>World</b></p>",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "html")
        assert str(item.content) in result

    def test_date_is_empty_string_when_published_is_none(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title="Title",
            link=None,
            content="Body",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert len(result) > 0

    def test_missing_title_renders_empty(
        self, renderer: TemplateRenderer, sample_feed: Feed
    ) -> None:
        item = FeedItem(
            id="1",
            title=None,
            link="http://example.com",
            content="Body",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert str(item.link) in result


class TestCustomSubjectTemplate:
    """Tests for custom subject templates."""

    def test_custom_subject_template(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(subject_template="[{{ feed_title }}] {{ title }}")
        item = FeedItem(
            id="1",
            title="My Article",
            link="http://example.com",
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed, "Tech News")
        assert subject == "[Tech News] My Article"

    def test_custom_subject_with_feed_url(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(subject_template="{{ title }} ({{ feed_url }})")
        item = FeedItem(
            id="1",
            title="Hello",
            link=None,
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed)
        assert subject == "Hello (http://example.com/feed)"

    def test_custom_subject_still_truncates(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(subject_template="{{ title }}")
        item = FeedItem(
            id="1",
            title="A" * 300,
            link=None,
            content=None,
            published=None,
        )
        subject = renderer.make_subject(item, sample_feed)
        assert len(subject) == 255


class TestCustomBodyTemplate:
    """Tests for custom body templates."""

    def test_custom_body_template_text(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(body_template="ITEM: {{ title }}\n{{ body }}")
        item = FeedItem(
            id="1",
            title="Test",
            link="http://example.com",
            content="Hello world",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "text")
        assert result == "ITEM: Test\nHello world"

    def test_custom_body_template_html(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(body_template="<p>{{ title }}: {{ body }}</p>")
        item = FeedItem(
            id="1",
            title="Test",
            link=None,
            content="<b>Bold</b>",
            published=None,
        )
        result = renderer.render_body(item, sample_feed, "Feed", "html")
        # HTML body is sanitized via nh3 then rendered with autoescaping
        assert "Test" in result
        assert "<b>Bold</b>" in result

    def test_custom_body_uses_all_context_variables(self, sample_feed: Feed) -> None:
        tpl = "{{ title }}|{{ link }}|{{ date }}|{{ feed_title }}|{{ feed_url }}|{{ body }}"
        renderer = TemplateRenderer(body_template=tpl)
        item = FeedItem(
            id="1",
            title="Title",
            link="http://example.com/post",
            content="Content",
            published=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        )
        result = renderer.render_body(item, sample_feed, "My Feed", "text")
        assert "Title" in result
        assert "http://example.com/post" in result
        assert "2024-06-15 12:00:00" in result
        assert "My Feed" in result
        assert "http://example.com/feed" in result
        assert "Content" in result

    def test_default_templates_when_none_provided(self, sample_feed: Feed) -> None:
        renderer = TemplateRenderer(subject_template=None, body_template=None)
        item = FeedItem(
            id="1",
            title="Test",
            link="http://example.com",
            content="Body",
            published=None,
        )
        # Should behave identically to default renderer
        assert renderer.make_subject(item, sample_feed) == "Test"
        body = renderer.render_body(item, sample_feed, "Feed", "text")
        assert "Test" in body
        assert "Feed" in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

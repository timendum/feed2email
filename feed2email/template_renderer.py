"""Template renderer for feed2email email bodies."""

import nh3
from jinja2 import Environment
from markupsafe import Markup

from feed2email.models import Feed, FeedItem

# Built-in subject template
_SUBJECT_TEMPLATE = "{{ title }}"

# Built-in plain text template
_PLAIN_TEXT_TEMPLATE = """\
{{ title }}
{{ link }}

{{ body }}

---
Feed: {{ feed_title }}
URL: {{ feed_url }}
Date: {{ date }}
"""

# Built-in HTML template
_HTML_TEMPLATE = """\
<html>
<body>
<h1><a href="{{ link }}">{{ title }}</a></h1>
<div>{{ body }}</div>
<hr>
<p>Feed: <a href="{{ feed_url }}">{{ feed_title }}</a></p>
<p>Date: {{ date }}</p>
</body>
</html>
"""


class TemplateRenderer:
    """Renders feed items into email bodies using Jinja2 templates."""

    def __init__(self) -> None:
        self._text_env = Environment(autoescape=False)  # noqa: S701 - plain text output, no XSS risk
        self._html_env = Environment(autoescape=True)

        self._subject_template = self._text_env.from_string(_SUBJECT_TEMPLATE)
        self._text_template = self._text_env.from_string(_PLAIN_TEXT_TEMPLATE)
        self._html_template = self._html_env.from_string(_HTML_TEMPLATE)

    def render_body(
        self,
        feed_item: FeedItem,
        feed: Feed,
        feed_title: str,
        format: str,
    ) -> str:
        """Render a feed item into an email body.

        Args:
            feed_item: The feed item to render.
            feed: The feed the item belongs to.
            feed_title: Title of the feed.
            format: Either 'text' or 'html'.

        Returns:
            The rendered email body string.
        """
        # Body: use content or empty string
        body = feed_item.content or ""

        # For plain text format, strip HTML from body
        if format == "text":
            body = nh3.clean(body, tags=set())

        context = self._make_context(feed_item, feed, feed_title)
        context["body"] = body

        if format == "html":
            context["body"] = Markup(nh3.clean(body))  # noqa: S704 - nh3 clean
            return self._html_template.render(**context)
        return self._text_template.render(**context)

    def _make_context(self, feed_item: FeedItem, feed: Feed, feed_title: str) -> dict[str, str]:
        date = ""
        if feed_item.published is not None:
            date = feed_item.published.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "title": feed_item.title or "No Title",
            "link": feed_item.link or "",
            "date": date,
            "feed_id": str(feed.id),
            "feed_title": feed_title,
            "feed_url": feed.url,
        }

    def make_subject(self, feed_item: FeedItem, feed: Feed, feed_title: str = "") -> str:
        """Construct the email subject line from a feed item and its feed.
        Truncates result to 255 characters.

        Args:
            feed_item: The feed item to render.
            feed: The feed the item belongs to.
            feed_title: Title of the feed (from fetch result).
        """
        context = self._make_context(feed_item, feed, feed_title)
        subject = self._subject_template.render(**context)
        return subject[:255]

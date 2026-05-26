"""Template renderer for feed2email email bodies."""

import re

from jinja2 import Environment

from feed2email.models import FeedItem

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
        self._env = Environment(autoescape=True)
        self._text_template = self._env.from_string(_PLAIN_TEXT_TEMPLATE)
        self._html_template = self._env.from_string(_HTML_TEMPLATE)

    def render(
        self,
        feed_item: FeedItem,
        feed_title: str,
        feed_url: str,
        format: str,
    ) -> str:
        """Render a feed item into an email body.

        Args:
            feed_item: The feed item to render.
            feed_title: Title of the feed.
            feed_url: URL of the feed.
            format: Either 'text' or 'html'.

        Returns:
            The rendered email body string.
        """
        # Body: use content or empty string
        body = feed_item.content or ""

        # For plain text format, strip HTML from body
        if format == "text":
            body = self.strip_html(body)

        # Format the date
        date = ""
        if feed_item.published is not None:
            date = feed_item.published.strftime("%Y-%m-%d %H:%M:%S")

        context = {
            "title": feed_item.title or "",
            "link": feed_item.link or "",
            "body": body,
            "date": date,
            "feed_title": feed_title,
            "feed_url": feed_url,
        }

        if format == "html":
            return self._html_template.render(**context)
        return self._text_template.render(**context)

    def make_subject(self, feed_item: FeedItem) -> str:
        """Construct the email subject line from a feed item.

        Fallback chain: title (truncated to 255 chars) -> link -> "No Title"
        """
        if feed_item.title:
            return feed_item.title[:255]
        if feed_item.link:
            return feed_item.link
        return "No Title"

    @staticmethod
    def strip_html(html: str) -> str:
        """Remove all HTML tags while preserving text content between tags.

        Args:
            html: A string potentially containing HTML tags.

        Returns:
            The text content with all HTML tags removed.
        """
        return re.sub(r"<[^>]*>", "", html)

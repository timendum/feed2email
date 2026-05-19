"""Data classes and constants."""

from dataclasses import dataclass
from datetime import datetime

VALID_CONFIG_KEYS = [
    "smtp.host",
    "smtp.port",
    "smtp.from",
    "smtp.user",
    "smtp.password",
    "smtp.encryption",
    "default-recipient",
    "user-agent",
]

REQUIRED_SMTP_KEYS = [
    "smtp.host",
    "smtp.port",
    "smtp.from",
    "smtp.encryption",
]


@dataclass
class Feed:
    """Represents a monitored RSS/Atom feed."""

    id: int
    url: str
    recipient: str | None
    dedup_key: str  # 'id' | 'link' | 'title'
    format: str  # 'text' | 'html'
    item_date: bool
    paused: bool
    created_at: datetime


@dataclass
class SmtpConfig:
    """SMTP server configuration."""

    host: str
    port: int
    from_address: str
    encryption: str  # 'none' | 'starttls' | 'ssl'
    username: str | None = None
    password: str | None = None


@dataclass
class FeedItem:
    """A single item parsed from a feed."""

    id: str | None
    title: str | None
    link: str | None
    content: str | None
    published: datetime | None


@dataclass
class FetchResult:
    """Result of fetching and parsing a feed."""

    success: bool
    items: list[FeedItem]
    feed_title: str
    error: str | None = None


@dataclass
class EmailMessage:
    """An email message ready to be sent."""

    recipient: str
    subject: str
    body: str
    content_type: str  # 'text/plain' or 'text/html'
    date: datetime
    feed_id: str | None = None
    item_url: str | None = None
    item_id: str | None = None
    user_agent: str | None = None


@dataclass
class SendResult:
    """Result of sending an email."""

    success: bool
    error: str | None = None


@dataclass
class RunResult:
    """Result of a full run cycle."""

    feeds_processed: int = 0
    feeds_failed: int = 0
    items_sent: int = 0
    items_failed: int = 0

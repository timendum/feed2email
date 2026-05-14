"""Data classes and constants."""

from dataclasses import dataclass
from datetime import datetime

REQUIRED_SMTP_KEYS = [
    "smtp.host",
    "smtp.port",
    "smtp.user",
    "smtp.password",
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
    username: str
    password: str
    encryption: str  # 'none' | 'starttls' | 'ssl'


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


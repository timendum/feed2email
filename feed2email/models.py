"""Data classes, constants, and validation functions."""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

REQUIRED_KEYS = (
    "smtp.host",
    "smtp.port",
    "smtp.from",
    "smtp.encryption",
    "default-recipient",
)

VALID_CONFIG_KEYS = (
    *REQUIRED_KEYS,
    "smtp.user",
    "smtp.password",
    "smtp.encryption",
    "user-agent",
)


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


# --- Validation functions ---


def validate_url(url: str) -> bool:
    """Check URL has http/https scheme and is well-formed."""
    try:
        result = urlparse(url)
    except Exception:
        return False
    return result.scheme in ("http", "https") and bool(result.netloc)


def validate_email(email: str) -> bool:
    """Check email is well-formed."""
    if "@" not in email:
        return False
    local, _, domain = email.rpartition("@")
    if not local:
        return False
    if not domain:
        return False
    if "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def validate_port(port: int) -> bool:
    """Check port is valid."""
    return isinstance(port, int) and 1 <= port <= 65535

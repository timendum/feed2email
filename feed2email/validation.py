"""Validation functions for URLs, email addresses, and ports."""

from urllib.parse import urlparse


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

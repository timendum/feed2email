"""Data classes and constants."""

from dataclasses import dataclass
from datetime import datetime

@dataclass
class Feed:
    """Represents a monitored RSS/Atom feed."""

    id: int
    url: str
    recipient: str
    dedup_key: str  # 'id' | 'link' | 'title'
    format: str  # 'text' | 'html'
    item_date: bool
    paused: bool
    created_at: datetime

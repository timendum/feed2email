from collections.abc import Generator
from pathlib import Path

import pytest

from feed2email.db import Database
from feed2email.feed_manager import FeedManager


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database]:
    """Create a temporary initialized Database instance."""
    database = Database(path=tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def feed_manager(db: Database) -> FeedManager:
    """Create a FeedManager instance backed by the test database."""
    return FeedManager(db)

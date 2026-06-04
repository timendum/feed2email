from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from feed2email.db import Database
from feed2email.feed_manager import FeedManager
from feed2email.models import FetchResult


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


@pytest.fixture
def patched_manager(feed_manager: FeedManager) -> FeedManager:
    """A FeedManager with its fetcher stubbed to return an empty successful result.

    Override the return value in individual tests when needed::

        patched_manager._fetcher.fetch.return_value = FetchResult(...)
    """
    feed_manager._fetcher.fetch = MagicMock(
        return_value=FetchResult(success=True, items=[], feed_title="Test Feed")
    )
    return feed_manager


@pytest.fixture
def patch_fetch():
    """Patch FeedFetcher.fetch to return an empty successful result.

    Use this fixture in CLI tests to avoid real HTTP calls during feed addition.
    The mock is yielded in case a test needs to inspect or customize it.
    """
    with patch(
        "feed2email.feed_manager.FeedFetcher.fetch",
        return_value=FetchResult(success=True, items=[], feed_title="Test Feed"),
    ) as mock:
        yield mock

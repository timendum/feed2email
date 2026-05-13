from typing import Generator

from pathlib import Path
import pytest

from feed2email.db.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Create a temporary initialized Database instance."""
    database = Database(path=tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()
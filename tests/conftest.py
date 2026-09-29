import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from database_connection import get_engine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    return get_engine()


@pytest.fixture()
def conn(engine):
    """A connection whose work is always rolled back, so tests never change data."""
    connection = engine.connect()
    trans = connection.begin()
    yield connection
    trans.rollback()
    connection.close()

"""Unit test for app.db.session.get_db, the FastAPI DB-session dependency."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_db


def test_get_db_yields_a_session_and_closes_it_after_use() -> None:
    """FastAPI drives this generator by calling next() once to get the
    session, then next() again after the request to run the `finally`
    block -- this replicates that protocol directly."""
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)

    session.close = MagicMock()  # type: ignore[method-assign]
    with pytest.raises(StopIteration):
        next(gen)
    session.close.assert_called_once()

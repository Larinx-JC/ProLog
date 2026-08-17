"""SQLAlchemy engine/session wiring, shared by the whole app.

Nothing imports this module yet in Section 1 — it exists so Alembic and
later sections (which add ORM models and DB-backed routes) have a single
place to get a session from, rather than each reinventing engine setup.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base every ORM model inherits from."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session, closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

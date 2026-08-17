"""Shared pytest fixtures for the backend test suite."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.main import create_app
from app.models import Material, Role, Run, RunStatus, User
from app.models.role import ADMIN


@pytest.fixture
def client() -> TestClient:
    """A TestClient wrapping a freshly-built app instance, isolated per test."""
    return TestClient(create_app())


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A fresh SQLite in-memory DB per test, schema created directly from
    the ORM models (not via Alembic).

    This exercises real model/relationship/constraint behavior fast and
    without a running database. It does NOT validate that Alembic's
    migration matches these models against the real MySQL dialect --
    that's covered separately by the CI Alembic-against-mysql:8.4 smoke
    test, which is what actually runs in production.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def admin_role(db_session: Session) -> Role:
    """A seeded Admin role, for tests that need any valid Role FK target."""
    role = Role(code=ADMIN, display_name="管理员")
    db_session.add(role)
    db_session.flush()
    return role


@pytest.fixture
def user(db_session: Session, admin_role: Role) -> User:
    """A minimal valid User, for tests that need any valid creator/actor FK target."""
    u = User(
        name="Test User",
        account="test.user",
        password_hash="not-a-real-hash",
        role_id=admin_role.id,
    )
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def material(db_session: Session) -> Material:
    """A minimal valid Material, for tests that need any valid Run FK target."""
    m = Material(
        material_no="M-TEST",
        standard_value=Decimal("100.00"),
        upper_limit=Decimal("105.00"),
        lower_limit=Decimal("95.00"),
        thickness_min=Decimal("5.00"),
        thickness_max=Decimal("7.00"),
        deviation_pct_threshold=Decimal("5.00"),
    )
    db_session.add(m)
    db_session.flush()
    return m


@pytest.fixture
def run(db_session: Session, material: Material, user: User) -> Run:
    """A minimal valid, active Run."""
    r = Run(
        run_code="RUN-TEST-0001",
        material_id=material.id,
        standard_value=material.standard_value,
        raw_material_batch="B-TEST",
        interval_seconds=60,
        status=RunStatus.ACTIVE,
        start_time=datetime(2026, 3, 9, 8, 0, 0),
        created_by_id=user.id,
    )
    db_session.add(r)
    db_session.flush()
    return r

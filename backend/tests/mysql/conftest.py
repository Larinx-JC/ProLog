"""MySQL integration fixtures: only the explicitly designated disposable CI database."""

import os

import pytest
from alembic.config import Config
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import get_settings
from app.core.security import Passwords
from app.services.auth import AuthService
from tests.auth_fixtures import FrozenClock
from tests.settings import SettingsWithoutDotenv


@pytest.fixture
def mysql_auth(monkeypatch: pytest.MonkeyPatch, passwords: Passwords):
    """Reset only prolog_test, then exercise the actual migrations on MySQL 8.4."""
    url = os.environ.get("PROLOG_TEST_MYSQL_URL")
    if not url:
        pytest.skip("Requires explicitly configured disposable MySQL test database")
    parsed = make_url(url)
    if parsed.drivername != "mysql+pymysql" or parsed.database != "prolog_test":
        pytest.fail("MySQL integration refuses any database except mysql+pymysql prolog_test")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.check(config)
        factory = sessionmaker(bind=engine, autoflush=False)
        settings = SettingsWithoutDotenv(app_env="test", secret_key="integration-test-" * 4)
        yield AuthService(factory, settings, FrozenClock(), passwords)
    finally:
        # Six-place production data cannot be downgraded losslessly to scale 2.
        # Clear only this previously validated disposable test database first;
        # leave the production migration's loss-prevention guard intact.
        tables = MetaData()
        tables.reflect(bind=engine)
        with engine.begin() as connection:
            for table in reversed(tables.sorted_tables):
                if table.name != "alembic_version":
                    connection.execute(table.delete())
        engine.dispose()
        get_settings.cache_clear()

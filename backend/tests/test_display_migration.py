"""Display schema constraints and preservation across actual populated migrations."""

import re
from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import get_settings
from tests.test_production_migrations import seed_legacy_production


def test_offline_mysql_display_seed_has_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated upgrade SQL must populate the required timestamp without execution parameters."""
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://test:test@localhost/prolog_test")
    get_settings.cache_clear()
    output = StringIO()
    try:
        command.upgrade(Config("alembic.ini", output_buffer=output), "head", sql=True)
        seed = next(s for s in output.getvalue().split(";") if "INSERT INTO display_settings" in s)
        assert "a.rounding, NULL" not in seed
        assert re.search(r"a\.rounding, '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", seed)
    finally:
        get_settings.cache_clear()


def production_rows(engine) -> dict:
    """Read exact persisted history independently of presentation and ORM serializers."""
    with engine.connect() as db:
        return {
            name: list(db.execute(text(f"SELECT * FROM {name} ORDER BY id")))
            for name in ("materials", "runs", "measurements", "accuracy_versions")
        }


def assert_display_migration(config: Config, engine) -> None:
    """Seed prior production, migrate preferences and prove no recording data is rewritten."""
    command.downgrade(config, "b6d84e19a203")
    with engine.begin() as db:
        seed_legacy_production(db)
        db.execute(
            text(
                "INSERT INTO accuracy_versions (id, resistance_places, thickness_places, "
                "speed_places, "
                "length_places, result_places, rounding, calculation_version, created_at) "
                "VALUES (3, 4, 6, 2, 2, 2, 'half_even', 'target_v1', '2026-01-01')"
            )
        )
        db.execute(text("UPDATE production_settings SET accuracy_version_id=3 WHERE id=1"))
    before = production_rows(engine)
    command.upgrade(config, "head")
    command.check(config)
    assert production_rows(engine) == before
    with engine.connect() as db:
        assert db.execute(
            text(
                "SELECT resistance_places, thickness_places, rounding, revision "
                "FROM display_settings WHERE id=1"
            )
        ).one() == (4, 6, "half_even", 1)
    for assignment in (
        "resistance_places=-1",
        "thickness_places=7",
        "speed_places=7",
        "length_places=-1",
        "result_places=7",
        "rounding='truncate'",
        "revision=0",
        "id=2",
        "updated_by_id=999999",
    ):
        with pytest.raises(DBAPIError), engine.begin() as db:
            db.execute(text(f"UPDATE display_settings SET {assignment} WHERE id=1"))
    with engine.begin() as db:
        db.execute(text("UPDATE display_settings SET thickness_places=0 WHERE id=1"))
    command.downgrade(config, "b6d84e19a203")
    assert "display_settings" not in inspect(engine).get_table_names()
    assert production_rows(engine) == before
    command.upgrade(config, "head")
    command.check(config)


def test_populated_display_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise real revision operations and constraints on an isolated SQLite database."""
    url = f"sqlite:///{(tmp_path / 'display.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config, engine = Config("alembic.ini"), create_engine(url)
    # Migration SQLite connections omit FK enforcement; explicitly test that
    # constraint using this independent connection pool as well.
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record) -> None:
        """Make the display updater FK test meaningful on every SQLite connection."""
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        command.upgrade(config, "head")
        assert_display_migration(config, engine)
    finally:
        engine.dispose()
        get_settings.cache_clear()

"""Populated migration preservation and explicit refusal of lossy numeric downgrades."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from alembic import command
from app.core.config import get_settings


def seed_legacy_production(db: Connection) -> None:
    """Insert synthetic Section 3-era rows with historical uniformity statistics."""
    db.execute(
        text(
            "INSERT INTO users (id, name, account, password_hash, role_id, created_at, updated_at) "
            "SELECT 1, 'Legacy', 'legacy.test', 'test-only-hash', id, '2026-01-01', '2026-01-01' "
            "FROM roles WHERE code='admin'"
        )
    )
    db.execute(
        text(
            "INSERT INTO materials (id, material_no, standard_value, upper_limit, lower_limit, "
            "thickness_min, thickness_max, deviation_pct_threshold, created_at, updated_at) "
            "VALUES (1, 'LEGACY', 100.00, 110.00, 90.00, 0.01, 0.02, 5.00, "
            "'2026-01-01', '2026-01-01')"
        )
    )
    db.execute(
        text(
            "INSERT INTO runs (id, run_code, material_id, raw_material_batch, interval_seconds, "
            "standard_value, upper_limit, lower_limit, thickness_min, thickness_max, "
            "deviation_pct_threshold, start_time, created_by_id, created_at, updated_at) "
            "VALUES (1, 'LEGACY-RUN', 1, 'LEGACY-BATCH', 60, 100.00, 110.00, 90.00, 0.01, 0.02, "
            "5.00, '2026-01-01', 1, '2026-01-01', '2026-01-01')"
        )
    )
    db.execute(
        text(
            "INSERT INTO measurements (id, run_id, measurement_time, point_1, average_value, "
            "max_deviation, deviation_percent) "
            "VALUES (1, 1, '2026-01-01', 101.23, 100.00, 1.23, 1.23)"
        )
    )


def assert_preserved_and_loss_guard(config: Config, engine) -> None:
    """Check real migration data, policy backfill, drift and precision-loss rejection."""
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as db:
        row = db.execute(
            text(
                "SELECT point_1, deviation_percent, target_deviation_percent "
                "FROM measurements WHERE id=1"
            )
        ).one()
        assert str(row[0]).startswith("101.23") and str(row[1]).startswith("1.23")
        assert row[2] is None
        assert db.scalar(text("SELECT accuracy_version_id FROM runs WHERE id=1")) == 1
        assert (
            db.scalar(text("SELECT calculation_version FROM accuracy_versions WHERE id=1"))
            == "legacy"
        )
        assert db.scalar(text("SELECT thickness_places FROM accuracy_versions WHERE id=2")) == 3
        assert db.scalar(text("SELECT operator_abnormal_allowed FROM production_settings")) == 1
    with engine.begin() as db:
        db.execute(text("UPDATE measurements SET thickness = 0.006 WHERE id=1"))
    with pytest.raises(RuntimeError, match="without losing data"):
        command.downgrade(config, "7a9b31c4d502")
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "b6d84e19a203"
        assert str(db.scalar(text("SELECT thickness FROM measurements WHERE id=1"))).startswith(
            "0.006"
        )
    with engine.begin() as db:
        db.execute(text("UPDATE measurements SET thickness = 0.01 WHERE id=1"))
    command.downgrade(config, "7a9b31c4d502")
    with engine.connect() as db:
        assert str(db.scalar(text("SELECT point_1 FROM measurements WHERE id=1"))).startswith(
            "101.23"
        )
    command.upgrade(config, "head")
    command.check(config)


def test_populated_production_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a real temporary database, never create_all, to verify the new migration."""
    url = f"sqlite:///{(tmp_path / 'production-migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "7a9b31c4d502")
        with engine.begin() as db:
            seed_legacy_production(db)
        assert_preserved_and_loss_guard(config, engine)
    finally:
        engine.dispose()
        get_settings.cache_clear()

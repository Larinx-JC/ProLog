"""Actual migration parity and preservation checks on a disposable SQLite database."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import DefaultClause, MetaData, create_engine, false, inspect, text

from alembic import command
from app.core.config import get_settings
from app.db.session import Base
from scripts.verify_seed_data import EXPECTED_ROLES, fetch_seeded_roles


def test_migration_preserves_users_defaults_and_detects_default_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upgrade old synthetic data and prove server-default mismatches are detectable."""
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0c3dff882627")
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO users (name, account, password_hash, role_id, "
                    "created_at, updated_at) "
                    "SELECT 'Existing Admin', 'existing.admin', 'legacy-hash', id, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00' FROM roles WHERE code='admin'"
                )
            )
        command.upgrade(config, "head")
        command.check(config)
        assert fetch_seeded_roles(engine) == EXPECTED_ROLES
        with engine.connect() as db:
            original = db.execute(
                text("SELECT account, password_hash, activated_at FROM users")
            ).one()
            assert original[0:2] == ("existing.admin", "legacy-hash")
            assert original[2] is not None
            assert db.execute(text("SELECT bootstrap_completed FROM auth_state")).scalar_one() == 1
            context = MigrationContext.configure(db, opts={"compare_server_default": True})
            assert compare_metadata(context, Base.metadata) == []
            changed = MetaData()
            for table in Base.metadata.sorted_tables:
                table.to_metadata(changed)
            changed.tables["users"].c.is_active.server_default = DefaultClause(false())
            differences = compare_metadata(context, changed)
            assert any("modify_default" in str(diff) for diff in differences)
        command.downgrade(config, "0c3dff882627")
        with engine.connect() as db:
            assert db.execute(text("SELECT account FROM users")).scalar_one() == "existing.admin"
        assert "activated_at" not in {c["name"] for c in inspect(engine).get_columns("users")}
        command.downgrade(config, "base")
    finally:
        engine.dispose()
        get_settings.cache_clear()

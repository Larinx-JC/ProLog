"""Production-dialect persistence, migration, race and rollback acceptance tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier

import pytest
from alembic.config import Config
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import AccessGrant, AuditLog, Material, User
from app.services.auth import AuthService
from app.services.auth_types import AuthError
from scripts.verify_seed_data import EXPECTED_ROLES, fetch_seeded_roles
from tests.auth_fixtures import PASSWORD, REPLACEMENT, bootstrap_login, invite_login

pytestmark = pytest.mark.mysql


def race(first, second) -> list[str]:
    """Start two independent database operations together and return safe outcomes."""
    barrier = Barrier(2)

    def call(operation) -> str:
        """Synchronize competing requests without sleeps or shared ORM sessions."""
        barrier.wait(timeout=10)
        try:
            operation()
            return "ok"
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call, operation) for operation in (first, second)]
        return [future.result(timeout=30) for future in futures]


def test_mysql_bootstrap_race(mysql_auth: AuthService) -> None:
    """The singleton database lock permits exactly one initial Admin across workers."""
    auth = mysql_auth
    results = race(
        lambda: auth.bootstrap("first.admin", "First", PASSWORD),
        lambda: auth.bootstrap("second.admin", "Second", PASSWORD),
    )
    assert sorted(results) == ["bootstrap_already_completed", "ok"]
    with auth.factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1


@pytest.mark.parametrize("purpose", ["activation", "recovery"])
def test_mysql_single_use_grant_race(mysql_auth: AuthService, purpose: str) -> None:
    """Concurrent consumption cannot use a link twice or create two success audits."""
    auth = mysql_auth
    admin = bootstrap_login(auth)
    grant = auth.invite(admin.token, "operator.test", "Operator", "operator")
    if purpose == "recovery":
        auth.consume_grant(grant.token, "activation", PASSWORD, "setup")
        grant = auth.issue_grant(admin.token, grant.user.id, "recovery")
    results = race(
        lambda: auth.consume_grant(grant.token, purpose, PASSWORD, "client-a"),
        lambda: auth.consume_grant(grant.token, purpose, REPLACEMENT, "client-b"),
    )
    assert results.count("ok") == 1 and results.count("invalid_or_expired_link") == 1
    with auth.factory() as db:
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.action == f"{purpose}_completed")
            )
            == 1
        )


def test_mysql_final_admin_race(mysql_auth: AuthService) -> None:
    """Two Admins cannot simultaneously disable themselves and leave none active."""
    auth = mysql_auth
    first = bootstrap_login(auth)
    _, second = invite_login(auth, first, "admin", "second.admin")
    results = race(
        lambda: auth.change_user(first.token, first.user.id, None, False),
        lambda: auth.change_user(second.token, second.user.id, None, False),
    )
    assert results.count("ok") == 1 and results.count("final_admin_required") == 1


def test_mysql_decimal_constraints_fk_seeds_and_timestamp(mysql_auth: AuthService) -> None:
    """Use the migrated production schema for quantities, invalid writes and microseconds."""
    auth = mysql_auth
    assert fetch_seeded_roles(auth.factory.kw["bind"]) == EXPECTED_ROLES
    admin = bootstrap_login(auth)
    with auth.factory.begin() as db:
        material = Material(
            material_no="M-MYSQL",
            standard_value=Decimal("99999999.99"),
            lower_limit=Decimal("0.01"),
            upper_limit=Decimal("99999999.99"),
            thickness_min=Decimal("0.01"),
            thickness_max=Decimal("99.99"),
            deviation_pct_threshold=Decimal("0.01"),
        )
        db.add(material)
    with auth.factory() as db:
        value = db.scalar(select(Material.standard_value))
        assert value == Decimal("99999999.99") and isinstance(value, Decimal)
        for sql in [
            "UPDATE materials SET lower_limit=100, upper_limit=99",
            "UPDATE materials SET thickness_min=100, thickness_max=99",
            "UPDATE materials SET deviation_pct_threshold=-1",
            "UPDATE users SET role_id=999999",
        ]:
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(text(sql))
    auth.clock.value = datetime(2026, 9, 7, 12, 0, 0, 123456)
    current = auth.current(admin.token, activity=True)
    assert current.id == admin.user.id
    with auth.factory() as db:
        timestamp = db.execute(text("SELECT last_activity_at FROM login_sessions")).scalar_one()
        assert timestamp.microsecond == 123456


def test_mysql_audit_failure_rolls_back_account(mysql_auth: AuthService) -> None:
    """A failed audit write cannot leave a newly invited account or usable grant."""
    auth = mysql_auth
    admin = bootstrap_login(auth)
    engine = auth.factory.kw["bind"]

    def fail_audit(conn, cursor, statement, parameters, context, executemany) -> None:
        """Fail at the audit write while keeping the test database available."""
        if "INSERT INTO audit_logs" in statement:
            raise RuntimeError("injected failure")

    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError):
            auth.invite(admin.token, "rollback.user", "Rollback", "operator")
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    with auth.factory() as db:
        assert db.scalar(select(User).where(User.account == "rollback.user")) is None
        assert db.scalar(select(func.count(AccessGrant.id))) == 0


def test_mysql_upgrade_preserves_existing_user(mysql_auth: AuthService) -> None:
    """Upgrade real pre-authentication data and retain it when auth is downgraded."""
    config = Config("alembic.ini")
    engine = mysql_auth.factory.kw["bind"]
    command.downgrade(config, "0c3dff882627")
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO users (name, account, password_hash, role_id, created_at, updated_at) "
                "SELECT 'Existing Admin', 'existing.admin', 'legacy-hash', id, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00' FROM roles WHERE code='admin'"
            )
        )
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as db:
        original = db.execute(text("SELECT account, password_hash, activated_at FROM users")).one()
        assert tuple(original) == ("existing.admin", "legacy-hash", datetime(2026, 1, 1))
        assert db.execute(text("SELECT bootstrap_completed FROM auth_state")).scalar_one() == 1
    assert fetch_seeded_roles(engine) == EXPECTED_ROLES
    with pytest.raises(AuthError, match="bootstrap_already_completed"):
        mysql_auth.bootstrap("another.admin", "Another", PASSWORD)
    mysql_auth.recover_admin("existing.admin", PASSWORD)
    assert mysql_auth.login("existing.admin", PASSWORD, "local").user.role == "admin"
    command.downgrade(config, "0c3dff882627")
    with engine.connect() as db:
        assert db.execute(text("SELECT account FROM users")).scalar_one() == "existing.admin"
    command.upgrade(config, "head")

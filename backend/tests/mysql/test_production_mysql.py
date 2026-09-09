"""MySQL precision, migration, atomicity and independent-connection production races."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier

import pytest
from alembic.config import Config
from sqlalchemy import event, func, select, text

from alembic import command
from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import AuditLog, Measurement, ProductionRequest, Run, RunStatus
from app.services.auth import AuthService
from app.services.auth_types import AuthError
from tests.auth_fixtures import invite_login
from tests.production_fixtures import MATERIAL_RULES, SAMPLE, build_case, request_id
from tests.test_production_migrations import assert_preserved_and_loss_guard, seed_legacy_production

pytestmark = pytest.mark.mysql


def race(*operations) -> list:
    """Release independent service calls together; return actual results or explicit rejections."""
    barrier = Barrier(len(operations))

    def call(operation):
        """Synchronize without sleeps and let unexpected database failures fail the test."""
        barrier.wait(timeout=10)
        try:
            return operation()
        except (DomainError, AuthError) as error:
            return error.code

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(call, operation) for operation in operations]
        return [future.result(timeout=30) for future in futures]


def test_mysql_three_and_six_place_values_and_boundary_alarm(mysql_auth: AuthService) -> None:
    """MySQL preserves fractional thickness and exact boundary decisions after a fresh read."""
    case = build_case(mysql_auth)
    case.settings.update(
        case.admin.token,
        request_id(),
        1,
        replace(AccuracyPolicy(), resistance_places=6, thickness_places=6),
        True,
        "Six-place instrument",
    )
    run = case.start()
    sample = case.sample(run, point_1="102.000001", thickness="0.006001")
    assert sample.as_dict()["status"] == "abnormal"
    assert sample.as_dict()["target_deviation_percent"] == "2.00"
    loaded = case.runs.get_run(case.admin.token, run.id).as_dict()["measurements"][0]
    assert loaded["point_1"] == "102.000001" and loaded["thickness"] == "0.006001"
    with case.auth.factory() as db:
        row = db.get(Measurement, sample.id)
        assert row.point_1 == Decimal("102.000001") and row.thickness == Decimal("0.006001")


def test_mysql_concurrent_identical_request_creates_one_run(mysql_auth: AuthService) -> None:
    """A durable receipt deduplicates simultaneous requests on separate MySQL connections."""
    case = build_case(mysql_auth)
    key = request_id()

    def operation():
        """Submit the same client request through an independent service transaction."""
        return case.runs.start(case.admin.token, key, case.material.id, "B-RACE", 60)

    results = race(operation, operation)
    assert results[0] == results[1] and not isinstance(results[0], str)
    with case.auth.factory() as db:
        assert db.scalar(select(func.count(Run.id))) == 1
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "run_created")) == 1
        )


def test_mysql_concurrent_measurement_edits_cannot_overwrite(mysql_auth: AuthService) -> None:
    """Exactly one write may consume a run revision; no last-writer-wins loss occurs."""
    case = build_case(mysql_auth)
    run = case.start()

    def operation():
        """Submit a new request sharing the same optimistic run revision."""
        return case.sample(run)

    results = race(operation, operation)
    assert results.count("revision_conflict") == 1
    with case.auth.factory() as db:
        assert db.scalar(select(func.count(Measurement.id))) == 1
        assert db.get(Run, run.id).revision == 2


def test_mysql_measurement_versus_close(mysql_auth: AuthService) -> None:
    """A close freezes data; if the edit wins, closure must refresh its stale revision."""
    case = build_case(mysql_auth)
    run = case.start()
    sample = case.sample(run)
    version = sample.as_dict()["run_revision"]
    results = race(
        lambda: case.measurements.save(
            case.admin.token, request_id(), run.id, version, run.as_dict()["start_time"], SAMPLE
        ),
        lambda: case.runs.close(case.admin.token, request_id(), run.id, version),
    )
    assert sum(not isinstance(result, str) for result in results) == 1
    assert any(
        result in ("revision_conflict", "run_not_editable")
        for result in results
        if isinstance(result, str)
    )
    with case.auth.factory() as db:
        assert db.get(Run, run.id).revision == 3


def test_mysql_close_versus_review_and_double_review(mysql_auth: AuthService) -> None:
    """Review cannot precede closure and two final decisions cannot both commit."""
    case = build_case(mysql_auth)
    run = case.start()
    sample = case.sample(run)
    results = race(
        lambda: case.runs.close(
            case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"]
        ),
        lambda: case.reviews.review(
            case.admin.token, request_id(), run.id, 3, "approved", "Reviewed"
        ),
    )
    assert not isinstance(results[0], str)
    current = case.runs.get_run(case.admin.token, run.id)
    if current.as_dict()["status"] == "pending_review":
        results = race(
            *[
                lambda: case.reviews.review(
                    case.admin.token, request_id(), run.id, current.revision, "approved", "Reviewed"
                )
                for _ in range(2)
            ]
        )
        assert sum(not isinstance(result, str) for result in results) == 1
    with case.auth.factory() as db:
        assert db.get(Run, run.id).status == RunStatus.REVIEWED
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "run_reviewed")) == 1
        )


def test_mysql_material_update_versus_run_start(mysql_auth: AuthService) -> None:
    """A new run captures either full old or full new rules, never a mixed snapshot."""
    case = build_case(mysql_auth)
    results = race(
        lambda: case.materials.update(
            case.admin.token,
            request_id(),
            case.material.id,
            1,
            dict(
                MATERIAL_RULES, standard_value="200.00", upper_limit="210.00", lower_limit="190.00"
            ),
            True,
            "New standard",
        ),
        lambda: case.start(),
    )
    assert all(not isinstance(result, str) for result in results)
    rules = results[1].as_dict()["rules"]
    assert (rules["standard_value"], rules["upper_limit"], rules["lower_limit"]) in {
        ("100.00", "110.00", "90.00"),
        ("200.00", "210.00", "190.00"),
    }


def test_mysql_settings_update_versus_run_start(mysql_auth: AuthService) -> None:
    """The run policy is one immutable version even when settings are published concurrently."""
    case = build_case(mysql_auth)
    results = race(
        lambda: case.settings.update(
            case.admin.token,
            request_id(),
            1,
            replace(AccuracyPolicy(), resistance_places=4, thickness_places=6),
            True,
            "New instruments",
        ),
        lambda: case.start(),
    )
    assert all(not isinstance(result, str) for result in results)
    accuracy = results[1].as_dict()["accuracy"]
    assert (accuracy["resistance_places"], accuracy["thickness_places"]) in {(2, 3), (4, 6)}


def test_mysql_disable_user_versus_measurement(mysql_auth: AuthService) -> None:
    """Either recording precedes disablement or current authentication rejects the write."""
    case = build_case(mysql_auth)
    _, operator = invite_login(case.auth, case.admin)
    run = case.start(operator)
    results = race(
        lambda: case.auth.change_user(case.admin.token, operator.user.id, None, False),
        lambda: case.sample(run, operator),
    )
    assert not isinstance(results[0], str)
    assert not isinstance(results[1], str) or results[1] == "authentication_required"
    with pytest.raises(AuthError, match="authentication_required"):
        case.runs.get_run(operator.token, run.id)


def test_mysql_audit_failure_rolls_back_production(mysql_auth: AuthService) -> None:
    """A real InnoDB rollback removes readings, status changes and retry receipts together."""
    case = build_case(mysql_auth)
    run = case.start()
    key = request_id()
    engine = case.auth.factory.kw["bind"]

    def fail(conn, cursor, statement, parameters, context, executemany) -> None:
        """Fail the audit insertion after preceding production statements execute."""
        if "INSERT INTO audit_logs" in statement:
            raise RuntimeError("audit failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="audit failure"):
            case.measurements.save(
                case.admin.token,
                key,
                run.id,
                run.revision,
                run.as_dict()["start_time"],
                dict(SAMPLE, point_1="120.00"),
                slot_index=0,
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with case.auth.factory() as db:
        assert db.scalar(select(func.count(Measurement.id))) == 0
        assert db.get(Run, run.id).status == RunStatus.ACTIVE
        assert db.get(ProductionRequest, (case.admin.user.id, key)) is None


def test_mysql_populated_production_migration(mysql_auth: AuthService) -> None:
    """Exercise the populated upgrade and precision-loss downgrade guard on actual MySQL."""
    engine = mysql_auth.factory.kw["bind"]
    config = Config("alembic.ini")
    command.downgrade(config, "7a9b31c4d502")
    with engine.begin() as db:
        seed_legacy_production(db)
    assert_preserved_and_loss_guard(config, engine)
    with engine.connect() as db:
        assert db.scalar(text("SELECT COUNT(*) FROM users WHERE account='legacy.test'")) == 1

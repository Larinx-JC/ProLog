"""Unit tests for the Section 2 ORM models.

Run against a SQLite in-memory DB (see conftest.db_session) -- fast and
dependency-free. Alembic's actual migration is validated separately
against real MySQL by CI (see .github/workflows/ci.yml), since that's
what catches dialect-specific issues these tests can't.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    EntryMethod,
    Material,
    Measurement,
    MeasurementStatus,
    Role,
    Run,
    RunStatus,
    User,
)
from app.models.role import OPERATOR


def test_role_code_must_be_unique(db_session: Session, admin_role: Role) -> None:
    """Two roles can't share a code -- it's the stable identifier services
    compare permissions against."""
    db_session.add(Role(code=admin_role.code, display_name="Duplicate"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_user_role_relationship_is_bidirectional(db_session: Session, user: User) -> None:
    """A User's role and a Role's users collection must agree."""
    db_session.refresh(user)
    assert user.role.code == "admin"
    assert user in user.role.users


def test_material_decimal_precision_survives_round_trip(db_session: Session) -> None:
    """A DECIMAL(10,2) value must come back exactly as entered -- not
    rounded/drifted the way a binary float would (0.1 + 0.2 problem) --
    since this is compared directly against measurements for abnormality."""
    m = Material(
        material_no="M-PRECISE",
        standard_value=Decimal("122.50"),
        upper_limit=Decimal("128.00"),
        lower_limit=Decimal("117.00"),
        thickness_min=Decimal("6.00"),
        thickness_max=Decimal("8.00"),
        deviation_pct_threshold=Decimal("5.00"),
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)

    assert m.standard_value == Decimal("122.50")
    assert isinstance(m.standard_value, Decimal)


def test_run_snapshots_standard_value_independent_of_material(
    db_session: Session, material: Material, user: User
) -> None:
    """Changing a Material's current standard_value later must NOT change
    an already-created Run's snapshotted standard_value.

    This is the core correctness property that makes a separate
    material-standard-version-history table unnecessary: the Run itself
    is the historical record of what standard applied to it.
    """
    original_standard = material.standard_value
    r = Run(
        run_code="RUN-SNAPSHOT",
        material_id=material.id,
        standard_value=material.standard_value,
        raw_material_batch="B-1",
        interval_seconds=60,
        status=RunStatus.ACTIVE,
        start_time=datetime(2026, 3, 9, 8, 0, 0),
        created_by_id=user.id,
    )
    db_session.add(r)
    db_session.commit()

    material.standard_value = Decimal("999.99")
    db_session.commit()
    db_session.refresh(r)

    assert r.standard_value == original_standard
    assert r.standard_value != material.standard_value


def test_run_material_and_creator_relationships(run: Run, material: Material, user: User) -> None:
    """A Run's material/created_by relationships must resolve to the
    actual rows they were created with."""
    assert run.material.material_no == material.material_no
    assert run.created_by.account == user.account


def test_measurements_ordered_by_measurement_time(
    db_session: Session, run: Run, user: User
) -> None:
    """Run.measurements must come back in measurement_time order even
    when rows were inserted out of order (operators add rows live, but
    reviewers need them in chronological order)."""
    later = Measurement(
        run_id=run.id,
        measurement_time=datetime(2026, 3, 9, 8, 5, 0),
        recorded_by_id=user.id,
    )
    earlier = Measurement(
        run_id=run.id,
        measurement_time=datetime(2026, 3, 9, 8, 1, 0),
        recorded_by_id=user.id,
    )
    db_session.add_all([later, earlier])
    db_session.commit()
    db_session.refresh(run)

    assert [m.measurement_time for m in run.measurements] == [
        datetime(2026, 3, 9, 8, 1, 0),
        datetime(2026, 3, 9, 8, 5, 0),
    ]


def test_measurement_defaults_to_missing_and_manual_entry(db_session: Session, run: Run) -> None:
    """A newly added measurement row starts MISSING (no values yet) and
    MANUAL (no automated ingestion source) unless told otherwise."""
    m = Measurement(run_id=run.id, measurement_time=datetime(2026, 3, 9, 8, 0, 0))
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)

    assert m.status == MeasurementStatus.MISSING
    assert m.entry_method == EntryMethod.MANUAL


def test_run_status_column_rejects_invalid_value(db_session: Session, run: Run) -> None:
    """Assigning a status outside RunStatus must fail at flush, not
    silently store garbage the app would later choke on.

    validate_strings=True in app.models.enums.sa_enum is what makes this
    fail on every backend -- without it, SQLite (unlike MySQL's native
    ENUM) would happily write an invalid string through unvalidated.
    """
    run.status = "not_a_real_status"  # type: ignore[assignment]
    with pytest.raises(StatementError):
        db_session.flush()


def test_sa_enum_stores_string_value_not_python_member_name(db_session: Session, run: Run) -> None:
    """The DB column must store "pending_review" (the enum's .value), not
    "PENDING_REVIEW" (the Python attribute name) -- this is what
    app.models.enums.sa_enum's values_callable is for."""
    run.status = RunStatus.PENDING_REVIEW
    db_session.commit()

    raw = db_session.execute(
        text("SELECT status FROM runs WHERE id = :id"), {"id": run.id}
    ).scalar_one()
    assert raw == "pending_review"


def test_audit_log_target_id_has_no_fk_constraint(db_session: Session, user: User) -> None:
    """AuditLog.target_id is intentionally polymorphic (points at whatever
    table target_type names) -- it must accept an id with no matching row
    in any single table without raising an IntegrityError."""
    log = AuditLog(
        actor_id=user.id,
        target_type="material",
        target_id=999999,
        target_label="物料标准 M-DOES-NOT-EXIST",
        before_value="标准值: 64.8",
        after_value="标准值: 65.4",
        reason="原料批次更新，标准值校正",
    )
    db_session.add(log)
    db_session.commit()  # must not raise

    assert log.id is not None


def test_role_seed_values_are_distinct(db_session: Session) -> None:
    """Admin/Operator/Reviewer must be three genuinely distinct rows --
    a typo that collides two codes would silently merge two privilege
    levels into one."""
    admin = Role(code="admin", display_name="管理员")
    operator = Role(code=OPERATOR, display_name="操作员")
    reviewer = Role(code="reviewer", display_name="复核员")
    db_session.add_all([admin, operator, reviewer])
    db_session.commit()

    codes = {r.code for r in db_session.query(Role).all()}
    assert codes == {"admin", "operator", "reviewer"}


def test_repr_includes_a_human_identifying_field(
    db_session: Session, admin_role: Role, material: Material, run: Run, user: User
) -> None:
    """Every model's __repr__ should surface its natural identifier
    (code/account/material_no/run_code), not just <Class object at 0x...>
    -- this is what shows up in logs and debugger output."""
    log = AuditLog(target_type="run", target_label="test", actor_id=user.id)
    db_session.add(log)
    db_session.flush()
    measurement = Measurement(run_id=run.id, measurement_time=run.start_time)
    db_session.add(measurement)
    db_session.flush()

    assert admin_role.code in repr(admin_role)
    assert user.account in repr(user)
    assert material.material_no in repr(material)
    assert run.run_code in repr(run)
    assert str(run.id) in repr(measurement)
    assert "run" in repr(log)

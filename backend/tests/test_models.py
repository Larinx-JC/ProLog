"""Unit tests for the Section 2 ORM models.

Run against a SQLite in-memory DB (see conftest.db_session) -- fast and
dependency-free. Alembic's actual migration is validated separately
against real MySQL by CI (see .github/workflows/ci.yml), since that's
what catches dialect-specific issues these tests can't.
"""

import time
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


def test_timestamp_mixin_updated_at_advances_on_update(
    db_session: Session, material: Material
) -> None:
    """onupdate=utcnow (see TimestampMixin) must actually fire on a real
    update -- updated_at should move forward, not stay frozen at
    created_at. The sleep guarantees two genuinely different utcnow()
    values regardless of clock resolution on the test machine."""
    original_created_at = material.created_at
    original_updated_at = material.updated_at
    assert original_created_at == original_updated_at

    time.sleep(0.01)
    material.standard_value = Decimal("111.11")
    db_session.commit()
    db_session.refresh(material)

    assert material.created_at == original_created_at
    assert material.updated_at > original_updated_at


def test_run_snapshots_all_material_rules_independent_of_material(
    db_session: Session, material: Material, user: User
) -> None:
    """Changing ANY of a Material's rule fields later must NOT change an
    already-created Run's snapshotted copies.

    This covers every AbnormalityRulesMixin field, not just
    standard_value: if only standard_value were snapshotted (an earlier
    version of this model), editing e.g. upper_limit or
    deviation_pct_threshold after a run started would judge that run's
    later measurements by different rules than its earlier ones. This is
    the core correctness property that makes a separate
    material-standard-version-history table unnecessary: the Run itself
    is the historical record of what rules applied to it.
    """
    original = {
        "standard_value": material.standard_value,
        "upper_limit": material.upper_limit,
        "lower_limit": material.lower_limit,
        "thickness_min": material.thickness_min,
        "thickness_max": material.thickness_max,
        "deviation_check_enabled": material.deviation_check_enabled,
        "deviation_pct_threshold": material.deviation_pct_threshold,
        "thickness_check_enabled": material.thickness_check_enabled,
        "limits_check_enabled": material.limits_check_enabled,
    }
    r = Run(
        run_code="RUN-SNAPSHOT",
        material_id=material.id,
        raw_material_batch="B-1",
        interval_seconds=60,
        status=RunStatus.ACTIVE,
        start_time=datetime(2026, 3, 9, 8, 0, 0),
        created_by_id=user.id,
        **original,
    )
    db_session.add(r)
    db_session.commit()

    material.standard_value = Decimal("999.99")
    material.upper_limit = Decimal("999.99")
    material.lower_limit = Decimal("0.00")
    material.thickness_min = Decimal("0.00")
    material.thickness_max = Decimal("999.99")
    material.deviation_check_enabled = not original["deviation_check_enabled"]
    material.deviation_pct_threshold = Decimal("99.00")
    material.thickness_check_enabled = not original["thickness_check_enabled"]
    material.limits_check_enabled = not original["limits_check_enabled"]
    db_session.commit()
    db_session.refresh(r)

    for field, original_value in original.items():
        assert getattr(r, field) == original_value, f"{field} drifted from its snapshot"
        assert getattr(r, field) != getattr(material, field), f"{field} should now differ"


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
    in any single table without raising an IntegrityError.

    This only actually proves something now that SQLite foreign key
    enforcement is turned on for this fixture (see conftest.db_session) --
    with it off, any target_id would be silently accepted regardless of
    whether target_id had a real FK constraint or not.
    """
    log = AuditLog(
        actor_id=user.id,
        action="material_standard_changed",
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


def test_user_rejects_invalid_role_id(db_session: Session, admin_role: Role) -> None:
    """A User can't reference a role_id that doesn't exist -- proves FK
    enforcement is actually on (see conftest.db_session), not just that
    the column exists."""
    bogus_id = admin_role.id + 999
    db_session.add(
        User(name="X", account="x", password_hash="h", role_id=bogus_id)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_run_rejects_invalid_material_id(
    db_session: Session, material: Material, user: User
) -> None:
    """A Run can't reference a material_id that doesn't exist."""
    bogus_id = material.id + 999
    db_session.add(
        Run(
            run_code="RUN-BAD-MATERIAL",
            material_id=bogus_id,
            standard_value=material.standard_value,
            upper_limit=material.upper_limit,
            lower_limit=material.lower_limit,
            thickness_min=material.thickness_min,
            thickness_max=material.thickness_max,
            deviation_pct_threshold=material.deviation_pct_threshold,
            raw_material_batch="B-1",
            interval_seconds=60,
            start_time=datetime(2026, 3, 9, 8, 0, 0),
            created_by_id=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_measurement_rejects_invalid_run_id(db_session: Session, run: Run) -> None:
    """A Measurement can't reference a run_id that doesn't exist."""
    bogus_id = run.id + 999
    db_session.add(
        Measurement(run_id=bogus_id, measurement_time=datetime(2026, 3, 9, 8, 0, 0))
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_material_rejects_lower_limit_above_upper_limit(db_session: Session) -> None:
    """A material whose lower_limit exceeds its upper_limit is a
    structurally broken rule -- abnormality checks against it would be
    unsatisfiable (or worse, silently backwards). Rejected regardless of
    what Section 4's services intend to do with it."""
    db_session.add(
        Material(
            material_no="M-BAD-LIMITS",
            standard_value=Decimal("100.00"),
            upper_limit=Decimal("90.00"),
            lower_limit=Decimal("110.00"),
            thickness_min=Decimal("5.00"),
            thickness_max=Decimal("7.00"),
            deviation_pct_threshold=Decimal("5.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_run_rejects_lower_limit_above_upper_limit(
    db_session: Session, material: Material, user: User
) -> None:
    """The same constraint must exist on runs, not just materials --
    they share AbnormalityRulesMixin's fields but are separate tables
    with separately-declared constraints (see
    app.models.mixins.abnormality_rule_constraints)."""
    db_session.add(
        Run(
            run_code="RUN-BAD-LIMITS",
            material_id=material.id,
            standard_value=material.standard_value,
            upper_limit=Decimal("90.00"),
            lower_limit=Decimal("110.00"),
            thickness_min=material.thickness_min,
            thickness_max=material.thickness_max,
            deviation_pct_threshold=material.deviation_pct_threshold,
            raw_material_batch="B-1",
            interval_seconds=60,
            start_time=datetime(2026, 3, 9, 8, 0, 0),
            created_by_id=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_material_rejects_thickness_min_above_max(db_session: Session) -> None:
    """thickness_min above thickness_max is the same class of structurally
    broken rule as lower_limit > upper_limit."""
    db_session.add(
        Material(
            material_no="M-BAD-THICKNESS",
            standard_value=Decimal("100.00"),
            upper_limit=Decimal("105.00"),
            lower_limit=Decimal("95.00"),
            thickness_min=Decimal("9.00"),
            thickness_max=Decimal("7.00"),
            deviation_pct_threshold=Decimal("5.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_material_rejects_negative_deviation_threshold(db_session: Session) -> None:
    """A negative deviation_pct_threshold is meaningless -- percentages
    below zero don't correspond to any real tolerance."""
    db_session.add(
        Material(
            material_no="M-BAD-DEVIATION",
            standard_value=Decimal("100.00"),
            upper_limit=Decimal("105.00"),
            lower_limit=Decimal("95.00"),
            thickness_min=Decimal("5.00"),
            thickness_max=Decimal("7.00"),
            deviation_pct_threshold=Decimal("-1.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("bad_interval", [0, -1])
def test_run_rejects_zero_or_negative_interval_seconds(
    db_session: Session, material: Material, user: User, bad_interval: int
) -> None:
    """A measurement interval of zero or negative seconds can't drive any
    real monitoring cadence. Parameterized so "zero or negative" in the
    test name is actually what's covered, not just zero."""
    db_session.add(
        Run(
            run_code="RUN-BAD-INTERVAL",
            material_id=material.id,
            standard_value=material.standard_value,
            upper_limit=material.upper_limit,
            lower_limit=material.lower_limit,
            thickness_min=material.thickness_min,
            thickness_max=material.thickness_max,
            deviation_pct_threshold=material.deviation_pct_threshold,
            raw_material_batch="B-1",
            interval_seconds=bad_interval,
            start_time=datetime(2026, 3, 9, 8, 0, 0),
            created_by_id=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_run_pending_from_rejects_values_outside_active_or_abnormal(
    db_session: Session, run: Run
) -> None:
    """pending_from is documented (docs/data-model.md) as only ever being
    active/abnormal/NULL, but the column type is the full RunStatus enum
    (it has to match `status`'s type). REVIEWED is a perfectly valid
    RunStatus member -- it passes app.models.enums.sa_enum's
    validate_strings check -- so only this table-level CHECK constraint
    stops "pending review from reviewed" from being nonsense that's
    silently accepted."""
    run.pending_from = RunStatus.REVIEWED
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_run_pending_from_allows_null(run: Run) -> None:
    """Sanity check that the pending_from CHECK constraint's `IS NULL OR
    ...` clause doesn't itself break the common case: a fresh active run
    with no pending_from set yet."""
    assert run.pending_from is None


def test_run_rejects_end_time_before_start_time(db_session: Session, run: Run) -> None:
    """A run's end_time can never precede its start_time -- this is a
    structural invariant true regardless of workflow, unlike e.g.
    "status=reviewed implies reviewed_by is set", which is a workflow
    transition left to Section 4's services (see Run's docstring)."""
    run.end_time = run.start_time.replace(hour=run.start_time.hour - 1)
    with pytest.raises(IntegrityError):
        db_session.commit()


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
    log = AuditLog(action="run_created", target_type="run", target_label="test", actor_id=user.id)
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

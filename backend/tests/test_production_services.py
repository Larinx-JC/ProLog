"""End-to-end service invariants using real auth and foreign-key-enforced SQLite."""

import json
from dataclasses import asdict, replace

import pytest
from sqlalchemy import event, func, select

from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import (
    AccuracyVersion,
    AuditLog,
    Measurement,
    ProductionRequest,
    ProductionSettings,
    Run,
    RunStatus,
)
from app.services.auth import AuthService
from app.services.auth_types import AuthError
from app.services.production.base import stamp_update
from tests.auth_fixtures import invite_login
from tests.production_fixtures import MATERIAL_RULES, SAMPLE, ProductionCase, build_case, request_id


@pytest.fixture
def case(auth: AuthService) -> ProductionCase:
    """Compose the actual service layer against a fresh foreign-key-enforced database."""
    return build_case(auth)


def test_complete_run_through_self_review(case: ProductionCase) -> None:
    """Demonstrate correct measurement, closure, terminal review and explicit self-review audit."""
    run = case.start()
    sample = case.sample(run)
    assert sample.as_dict()["thickness"] == "0.007"
    assert sample.as_dict()["target_deviation_percent"] == "0.00"
    assert sample.as_dict()["deviation_percent"] == "0.00"
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"]
    )
    assert closed.as_dict()["status"] == "pending_review"
    final = case.reviews.review(
        case.admin.token,
        request_id(),
        run.id,
        closed.revision,
        "approved",
        "Checked the complete record",
    )
    assert final.as_dict()["status"] == "reviewed" and final.as_dict()["self_review"]
    assert final.as_dict()["missing_count_at_close"] == 0
    with case.auth.factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "run_reviewed"))
        assert audit.actor_id == case.admin.user.id
        assert audit.reason == "Checked the complete record"
        assert json.loads(audit.after_value)["self_review"] is True


def test_target_alarm_is_sticky_and_pending_review_resolution_is_enforced(
    case: ProductionCase,
) -> None:
    """Uniform wrong readings alarm; correction retains run abnormality and review requirements."""
    run = case.start()
    bad = case.sample(run, **{f"point_{i}": "110.00" for i in range(1, 5)})
    assert bad.as_dict()["target_deviation_percent"] == "10.00"
    assert bad.as_dict()["deviation_percent"] == "0.00"
    corrected = case.measurements.save(
        case.admin.token,
        request_id(),
        run.id,
        bad.as_dict()["run_revision"],
        run.as_dict()["start_time"],
        SAMPLE,
        slot_index=0,
        measurement_id=bad.id,
        expected_revision=bad.revision,
        reason="Corrected instrument transcription",
    )
    assert corrected.as_dict()["status"] == "completed"
    assert corrected.as_dict()["run_status"] == "abnormal"
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, corrected.as_dict()["run_revision"]
    )
    with pytest.raises(DomainError, match="invalid_review_resolution"):
        case.reviews.review(
            case.admin.token, request_id(), run.id, closed.revision, "approved", "Review"
        )
    result = case.reviews.review(
        case.admin.token,
        request_id(),
        run.id,
        closed.revision,
        "false_alarm",
        "Transcription corrected; originals retained in audit",
    )
    assert result.as_dict()["review_resolution"] == "false_alarm"


def test_scheduled_missing_samples_and_manual_samples_are_independent(case: ProductionCase) -> None:
    """Extra samples never erase missed scheduled intervals; no dashboard visit is required."""
    run = case.start()
    sample = case.sample(run)
    case.auth.clock.advance(120)
    extra = case.measurements.save(
        case.admin.token,
        request_id(),
        run.id,
        sample.as_dict()["run_revision"],
        case.auth.clock.now().isoformat() + "Z",
        SAMPLE,
    )
    schedule = case.runs.schedule(case.admin.token, run.id).as_dict()
    assert schedule["expected_count"] == 3 and schedule["missing_count"] == 2
    assert [slot["status"] for slot in schedule["slots"]] == ["completed", "missing", "missing"]
    assert (
        len(case.runs.schedule(case.admin.token, run.id, offset=1, limit=1).as_dict()["slots"]) == 1
    )
    with pytest.raises(DomainError, match="closure_exception_reason_required"):
        case.runs.close(case.admin.token, request_id(), run.id, extra.as_dict()["run_revision"])
    closed = case.runs.close(
        case.admin.token,
        request_id(),
        run.id,
        extra.as_dict()["run_revision"],
        "Instrument unavailable for two scheduled samples",
    )
    assert closed.as_dict()["missing_count_at_close"] == 2
    case.auth.clock.advance(120)
    assert case.runs.schedule(case.admin.token, run.id).as_dict()["expected_count"] == 3
    final = case.reviews.review(
        case.admin.token,
        request_id(),
        run.id,
        closed.revision,
        "approved",
        "Reviewed with the documented data gap",
    )
    assert final.as_dict()["missing_count_at_close"] == 2
    assert final.as_dict()["closure_exception_reason"]


def test_partial_alarm_missing_values_and_admin_exception(case: ProductionCase) -> None:
    """A partial bad row is incomplete and alarming; Operators cannot waive missing data."""
    _, operator = invite_login(case.auth, case.admin)
    run = case.start(operator)
    partial = case.sample(run, operator, point_1="120.00", point_2=None, meter_count=None)
    data = partial.as_dict()
    assert data["status"] == "missing" and data["run_status"] == "abnormal"
    assert data["average_value"] is None and data["missing_fields"] == ["point_2", "meter_count"]
    with pytest.raises(AuthError, match="incomplete_close_requires_admin"):
        case.runs.close(operator.token, request_id(), run.id, data["run_revision"], "Missing")
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, data["run_revision"], "Sample lost"
    )
    final = case.reviews.review(
        case.admin.token,
        request_id(),
        run.id,
        closed.revision,
        "confirmed_abnormal",
        "Recorded deviation and missing sample data",
    )
    assert final.as_dict()["self_review"] is False


def test_accuracy_and_rules_are_snapshotted_and_permissions_change_immediately(
    case: ProductionCase,
) -> None:
    """New policy/rules affect new runs; the current Operator switch affects existing work."""
    _, operator = invite_login(case.auth, case.admin)
    run = case.start(operator)
    sample = case.sample(run, operator, point_1="103.00")
    case.settings.update(
        case.admin.token,
        request_id(),
        1,
        replace(AccuracyPolicy(), resistance_places=3, thickness_places=4),
        False,
        "Restrict abnormal corrections to Admin",
    )
    with pytest.raises(AuthError, match="permission_denied"):
        case.measurements.save(
            operator.token,
            request_id(),
            run.id,
            sample.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            SAMPLE,
        )
    with pytest.raises(DomainError, match="excess_precision"):
        case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            sample.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            dict(SAMPLE, thickness="0.0071"),
        )
    case.materials.update(
        case.admin.token,
        request_id(),
        case.material.id,
        case.material.revision,
        dict(MATERIAL_RULES, standard_value="105.000"),
        True,
        "New target",
    )
    old = case.runs.get_run(case.admin.token, run.id).as_dict()
    new = case.start(operator).as_dict()
    assert old["accuracy"]["thickness_places"] == 3 and old["rules"]["standard_value"] == "100.00"
    assert new["accuracy"]["thickness_places"] == 4 and new["rules"]["standard_value"] == "105.000"
    with case.auth.factory() as db:
        assert db.scalar(select(func.count(AccuracyVersion.id))) == 2


def test_precision_reduction_cannot_round_active_materials(case: ProductionCase) -> None:
    """Reject a settings change that would lose current standards, with no partial publication."""
    with pytest.raises(DomainError, match="material_precision_conflict"):
        case.settings.update(
            case.admin.token,
            request_id(),
            1,
            replace(AccuracyPolicy(), thickness_places=2),
            True,
            "Try lower precision",
        )
    assert case.settings.get(case.admin.token).revision == 1


def test_role_ownership_and_current_account_state(case: ProductionCase) -> None:
    """Enforce view-only Reviewer, Operator ownership, Admin authority and immediate disablement."""
    _, operator = invite_login(case.auth, case.admin)
    _, reviewer = invite_login(case.auth, case.admin, "reviewer", "reviewer.test")
    run = case.start()
    assert case.runs.get_run(reviewer.token, run.id).id == run.id
    for denied in (
        lambda: case.start(reviewer),
        lambda: case.sample(run, operator),
        lambda: case.settings.get(operator.token),
        lambda: case.reviews.review(
            operator.token, request_id(), run.id, run.revision, "approved", "No"
        ),
        lambda: case.materials.create(operator.token, request_id(), "FORBIDDEN", MATERIAL_RULES),
    ):
        with pytest.raises(AuthError, match="permission_denied"):
            denied()
    owned = case.start(operator)
    case.auth.change_user(case.admin.token, operator.user.id, None, False)
    with pytest.raises(AuthError, match="authentication_required"):
        case.sample(owned, operator)


def test_retries_are_durable_scoped_and_conflicts_are_rejected(case: ProductionCase) -> None:
    """A committed retry returns the same result, while changed content cannot reuse its key."""
    key = request_id()
    first = case.runs.start(case.admin.token, key, case.material.id, "B-RETRY", 60)
    second = case.runs.start(case.admin.token, key, case.material.id, "B-RETRY", 60)
    assert first == second
    with pytest.raises(DomainError, match="request_conflict"):
        case.runs.start(case.admin.token, key, case.material.id, "B-DIFFERENT", 60)
    copy = first.as_dict()
    copy["rules"]["standard_value"] = "999.00"
    assert (
        case.runs.get_run(case.admin.token, first.id).as_dict()["rules"]["standard_value"]
        == "100.00"
    )
    with case.auth.factory() as db:
        assert db.scalar(select(func.count(Run.id))) == 1
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "run_created")) == 1
        )


def test_stale_revision_duplicate_slots_and_calculated_field_forgery(case: ProductionCase) -> None:
    """Prevent overwrites, duplicate scheduled samples, and caller-injected result values."""
    run = case.start()
    first = case.sample(run)
    with pytest.raises(DomainError, match="revision_conflict"):
        case.sample(run)
    with pytest.raises(DomainError, match="sample_already_exists"):
        case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            first.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            SAMPLE,
            slot_index=0,
        )
    with pytest.raises(DomainError, match="unknown_measurement_field"):
        case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            first.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            dict(SAMPLE, average_value="100.00"),
        )


def test_audit_failure_rolls_back_measurement_alarm_revision_and_receipt(
    case: ProductionCase,
) -> None:
    """Inject failure after writes and assert the complete transaction is rolled back."""
    run = case.start()
    engine = case.auth.factory.kw["bind"]

    def fail_audit(conn, cursor, statement, parameters, context, executemany) -> None:
        """Fail the actual audit insert after measurement and run writes have been flushed."""
        if "INSERT INTO audit_logs" in statement:
            raise RuntimeError("injected audit failure")

    key = request_id()
    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="injected audit failure"):
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
        event.remove(engine, "before_cursor_execute", fail_audit)
    with case.auth.factory() as db:
        row = db.get(Run, run.id)
        assert row.status == RunStatus.ACTIVE and row.revision == run.revision
        assert db.scalar(select(func.count(Measurement.id))) == 0
        assert db.get(ProductionRequest, (case.admin.user.id, key)) is None


@pytest.mark.parametrize("state", ["pending", "reviewed"])
def test_closed_and_reviewed_runs_are_immutable(case: ProductionCase, state: str) -> None:
    """Reject all measurement/closure writes after submission and repeat final review."""
    run = case.start()
    sample = case.sample(run)
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"]
    )
    if state == "reviewed":
        closed = case.reviews.review(
            case.admin.token, request_id(), run.id, closed.revision, "approved", "Final review"
        )
    for operation in (
        lambda: case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            closed.revision,
            run.as_dict()["start_time"],
            SAMPLE,
        ),
        lambda: case.runs.close(case.admin.token, request_id(), run.id, closed.revision),
    ):
        with pytest.raises(DomainError, match="run_not_editable"):
            operation()
    if state == "reviewed":
        with pytest.raises(DomainError, match="run_not_pending_review"):
            case.reviews.review(
                case.admin.token, request_id(), run.id, closed.revision, "approved", "Again"
            )


def test_review_reasons_and_corrupt_active_state_are_rejected(case: ProductionCase) -> None:
    """Do not accept blank review explanations or rows with contradictory lifecycle fields."""
    run = case.start()
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, run.revision, "No samples available"
    )
    with pytest.raises(DomainError, match="reason_required"):
        case.reviews.review(
            case.admin.token, request_id(), run.id, closed.revision, "approved", "  "
        )
    another = case.start()
    with case.auth.factory.begin() as db:
        db.get(Run, another.id).end_time = case.auth.clock.now()
    with pytest.raises(DomainError, match="inconsistent_active_state"):
        case.sample(another)


def test_deactivated_material_and_unknown_targets(case: ProductionCase) -> None:
    """Soft deactivation blocks new runs while preserving existing run history."""
    run = case.start()
    case.materials.update(
        case.admin.token,
        request_id(),
        case.material.id,
        case.material.revision,
        MATERIAL_RULES,
        False,
        "Material retired",
    )
    with pytest.raises(DomainError, match="material_unavailable"):
        case.start()
    assert case.sample(run).as_dict()["status"] == "completed"
    with pytest.raises(DomainError, match="run_not_found"):
        case.runs.get_run(case.admin.token, 999999)


def test_invalid_material_and_settings_requests(case: ProductionCase) -> None:
    """Reject missing/unknown fields, duplicate names, invalid flags and stale settings."""
    for values, code in (
        ({}, "missing_rule_field"),
        (dict(MATERIAL_RULES, made_up="1"), "unknown_rule_field"),
    ):
        with pytest.raises(DomainError, match=code):
            case.materials.create(case.admin.token, request_id(), "NEW", values)
    with pytest.raises(DomainError, match="material_exists"):
        case.materials.create(case.admin.token, request_id(), "M-PRODUCTION", MATERIAL_RULES)
    with pytest.raises(DomainError, match="material_not_found"):
        case.materials.update(
            case.admin.token, request_id(), 999999, 1, MATERIAL_RULES, True, "Reason"
        )
    with pytest.raises(DomainError, match="invalid_active_flag"):
        case.materials.update(
            case.admin.token, request_id(), case.material.id, 1, MATERIAL_RULES, "yes", "Reason"
        )
    with pytest.raises(DomainError, match="invalid_permission_switch"):
        case.settings.update(case.admin.token, request_id(), 1, AccuracyPolicy(), "yes", "Reason")
    with pytest.raises(DomainError, match="revision_conflict"):
        case.settings.update(case.admin.token, request_id(), 0, AccuracyPolicy(), True, "Reason")


def test_invalid_request_and_measurement_identifiers(case: ProductionCase) -> None:
    """Malformed retries, nonfinite payloads and cross-run sample identities fail explicitly."""
    with pytest.raises(DomainError, match="invalid_request_id"):
        case.runs.start(case.admin.token, "not-a-uuid", case.material.id, "B", 60)
    run = case.start()
    for values in (dict(SAMPLE, speed=float("nan")), dict(SAMPLE, speed=object())):
        with pytest.raises(DomainError, match="invalid_request_payload"):
            case.measurements.save(
                case.admin.token,
                request_id(),
                run.id,
                run.revision,
                run.as_dict()["start_time"],
                values,
            )
    with pytest.raises(DomainError, match="measurement_not_found"):
        case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            run.revision,
            run.as_dict()["start_time"],
            SAMPLE,
            measurement_id=999999,
            expected_revision=1,
            reason="Correction",
        )
    sample = case.sample(run)
    with pytest.raises(DomainError, match="sample_identity_immutable"):
        case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            sample.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            SAMPLE,
            measurement_id=sample.id,
            expected_revision=sample.revision,
            reason="Move to manual",
        )


def test_background_reads_do_not_extend_session(case: ProductionCase) -> None:
    """Polling production cannot defeat the owner's thirty-minute inactivity timeout."""
    run = case.start()
    case.auth.clock.advance(case.auth.settings.session_idle_seconds - 1)
    case.runs.get_run(case.admin.token, run.id)
    case.runs.schedule(case.admin.token, run.id)
    case.auth.clock.advance(1)
    with pytest.raises(AuthError, match="authentication_required"):
        case.runs.get_run(case.admin.token, run.id)


def test_late_recording_and_same_instant_updates_use_injected_clock(case: ProductionCase) -> None:
    """Keep observed/recorded times and prevent ORM onupdate replacing the service clock."""
    run = case.start()
    sample = case.sample(run)
    with case.auth.factory() as db:
        assert db.get(Run, run.id).updated_at == case.auth.clock.now()
    case.auth.clock.advance(120)
    corrected = case.measurements.save(
        case.admin.token,
        request_id(),
        run.id,
        sample.as_dict()["run_revision"],
        run.as_dict()["start_time"],
        SAMPLE,
        slot_index=0,
        measurement_id=sample.id,
        expected_revision=sample.revision,
        reason="Late correction",
    )
    assert corrected.as_dict()["measurement_time"] == run.as_dict()["start_time"]
    assert corrected.as_dict()["recorded_at"] != corrected.as_dict()["measurement_time"]


def test_review_of_previously_authored_measurement_is_self_review(case: ProductionCase) -> None:
    """An Admin remains a participant even after an Operator corrects the same measurement."""
    _, operator = invite_login(case.auth, case.admin)
    run = case.start(operator)
    sample = case.sample(run)
    corrected = case.measurements.save(
        operator.token,
        request_id(),
        run.id,
        sample.as_dict()["run_revision"],
        run.as_dict()["start_time"],
        SAMPLE,
        slot_index=0,
        measurement_id=sample.id,
        expected_revision=sample.revision,
        reason="Operator correction",
    )
    closed = case.runs.close(
        operator.token, request_id(), run.id, corrected.as_dict()["run_revision"]
    )
    result = case.reviews.review(
        case.admin.token,
        request_id(),
        run.id,
        closed.revision,
        "approved",
        "Reviewed my earlier entry and its correction",
    )
    assert result.as_dict()["self_review"] is True


@pytest.mark.parametrize("abnormal", [False, True])
@pytest.mark.parametrize("resolution", ["approved", "confirmed_abnormal", "false_alarm", "unknown"])
def test_review_resolution_matrix(case: ProductionCase, abnormal: bool, resolution: str) -> None:
    """Allow only the final decisions defined for each captured pre-review state."""
    run = case.start()
    sample = case.sample(run, point_1="103.00" if abnormal else "100.00")
    closed = case.runs.close(
        case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"]
    )
    permitted = {"confirmed_abnormal", "false_alarm"} if abnormal else {"approved"}
    if resolution in permitted:
        result = case.reviews.review(
            case.admin.token, request_id(), run.id, closed.revision, resolution, "Checked"
        )
        assert result.as_dict()["review_resolution"] == resolution
    else:
        with pytest.raises(DomainError, match="invalid_review_resolution"):
            case.reviews.review(
                case.admin.token, request_id(), run.id, closed.revision, resolution, "Checked"
            )
        assert case.runs.get_run(case.admin.token, run.id).revision == closed.revision


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("operation", ["measurement", "close"])
def test_operator_abnormal_control(case: ProductionCase, allowed: bool, operation: str) -> None:
    """Apply the current Admin switch to both recording and closing an owned Abnormal run."""
    _, operator = invite_login(case.auth, case.admin)
    run = case.start(operator)
    sample = case.sample(run, operator, point_1="103.00")
    case.settings.update(
        case.admin.token, request_id(), 1, AccuracyPolicy(), allowed, "Operational setting"
    )

    def write():
        """Exercise the selected production action with current authority and revision."""
        if operation == "close":
            return case.runs.close(
                operator.token, request_id(), run.id, sample.as_dict()["run_revision"]
            )
        return case.measurements.save(
            operator.token,
            request_id(),
            run.id,
            sample.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            SAMPLE,
        )

    if allowed:
        result = write().as_dict()
        assert result.get("run_status", result["status"]) in {"abnormal", "pending_review"}
    else:
        with pytest.raises(AuthError, match="permission_denied"):
            write()
        assert (
            case.runs.get_run(case.admin.token, run.id).revision == sample.as_dict()["run_revision"]
        )


def test_transition_retries_do_not_repeat_final_audits(case: ProductionCase) -> None:
    """Retry closure and review after finalization without reapplying either transition."""
    run = case.start()
    sample = case.sample(run)
    close_key, review_key = request_id(), request_id()
    closed = case.runs.close(case.admin.token, close_key, run.id, sample.as_dict()["run_revision"])
    final = case.reviews.review(
        case.admin.token, review_key, run.id, closed.revision, "approved", "Checked"
    )
    assert (
        case.runs.close(case.admin.token, close_key, run.id, sample.as_dict()["run_revision"])
        == closed
    )
    assert (
        case.reviews.review(
            case.admin.token, review_key, run.id, closed.revision, "approved", "Checked"
        )
        == final
    )
    with case.auth.factory() as db:
        for action in ("run_closed_for_review", "run_reviewed"):
            assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == action)) == 1


def test_edited_material_does_not_change_existing_run_alarm(case: ProductionCase) -> None:
    """A target edit changes new runs while recording still evaluates the original snapshot."""
    original = case.start()
    case.materials.update(
        case.admin.token,
        request_id(),
        case.material.id,
        1,
        dict(MATERIAL_RULES, standard_value="105.00"),
        True,
        "Updated target",
    )
    newer = case.start()
    assert case.sample(original).as_dict()["alarm_codes"] == []
    assert case.sample(newer).as_dict()["run_status"] == "abnormal"


@pytest.mark.parametrize(
    "field,value",
    [
        ("end_time", None),
        ("pending_from", None),
        ("reviewed_by_id", 1),
        ("reviewed_at", "now"),
        ("review_resolution", "approved"),
        ("review_reason", "Existing"),
        ("missing_count_at_close", None),
        ("missing_count_at_close", -1),
        ("closure_exception_reason", None),
    ],
)
def test_inconsistent_pending_state_cannot_be_reviewed(
    case: ProductionCase,
    field: str,
    value: object,
) -> None:
    """Reject contradictory final metadata before a review can legitimize corrupted state."""
    run = case.start()
    closed = case.runs.close(case.admin.token, request_id(), run.id, run.revision, "Lost sample")
    with case.auth.factory.begin() as db:
        setattr(db.get(Run, run.id), field, case.auth.clock.now() if value == "now" else value)
    with pytest.raises(DomainError, match="inconsistent_review_state"):
        case.reviews.review(
            case.admin.token, request_id(), run.id, closed.revision, "approved", "Checked"
        )
    with case.auth.factory() as db:
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "run_reviewed")) == 0
        )


def test_legacy_history_does_not_invent_missed_samples(case: ProductionCase) -> None:
    """Legacy records remain readable without retroactively applying scheduled-sample rules."""
    case.materials.update(
        case.admin.token,
        request_id(),
        case.material.id,
        1,
        dict(MATERIAL_RULES, thickness_min="0.01", thickness_max="0.02"),
        True,
        "Legacy fixture",
    )
    run = case.start()
    sample = case.sample(run, thickness="0.01")
    with case.auth.factory.begin() as db:
        db.add(
            AccuracyVersion(
                id=1,
                **asdict(AccuracyPolicy(thickness_places=2)),
                calculation_version="legacy",
                created_at=case.auth.clock.now(),
            )
        )
        db.flush()
        legacy = db.get(Run, run.id)
        legacy.accuracy_version_id = 1
        stamp_update(legacy, case.auth.clock.now())
    case.auth.clock.advance(120)
    result = case.runs.get_run(case.admin.token, run.id).as_dict()
    assert result["missing_count"] is None
    assert result["measurements"][0]["id"] == sample.id
    with pytest.raises(DomainError, match="legacy_schedule_unavailable"):
        case.runs.schedule(case.admin.token, run.id)
    with pytest.raises(DomainError, match="legacy_run_read_only"):
        case.runs.close(case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"])


def test_missing_configuration_fails_closed(case: ProductionCase) -> None:
    """Never guess settings when required configuration or a run policy is missing."""
    run = case.start()
    with case.auth.factory.begin() as db:
        db.delete(db.get(ProductionSettings, 1))
        db.get(Run, run.id).accuracy_version_id = None
    with pytest.raises(DomainError, match="production_unavailable"):
        case.settings.get(case.admin.token)
    with pytest.raises(DomainError, match="accuracy_policy_unavailable"):
        case.runs.get_run(case.admin.token, run.id)


def test_unknown_runs_and_invalid_schedule_pages(case: ProductionCase) -> None:
    """Report absent production records consistently and bound schedule resource use."""
    for operation in (
        lambda: case.runs.schedule(case.admin.token, 999999),
        lambda: case.runs.close(case.admin.token, request_id(), 999999, 1),
        lambda: case.reviews.review(
            case.admin.token, request_id(), 999999, 1, "approved", "Checked"
        ),
    ):
        with pytest.raises(DomainError, match="run_not_found"):
            operation()
    for offset, limit in ((-1, 100), (0, 201), (0, 0), (True, 1)):
        with pytest.raises(DomainError, match="invalid_page"):
            case.runs.schedule(case.admin.token, 1, offset, limit)


def test_backwards_server_clock_cannot_close_before_last_write(case: ProductionCase) -> None:
    """Preserve production chronology when the server clock moves behind its last write."""
    _, operator = invite_login(case.auth, case.admin)
    case.auth.clock.advance(10)
    run = case.start(operator)
    case.auth.clock.advance(-1)
    with pytest.raises(DomainError, match="server_clock_moved_backwards"):
        case.runs.close(case.admin.token, request_id(), run.id, run.revision, "No sample")
    with case.auth.factory() as db:
        assert db.get(Run, run.id).status == RunStatus.ACTIVE

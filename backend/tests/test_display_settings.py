"""Presentation changes preserve recorded history, alarms, authority and retry semantics."""

import json
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import pytest
from sqlalchemy import event, select

from app.domain.display import MEASUREMENT_QUANTITIES, DisplayFormatter
from app.domain.numeric import MAX_RESULT, AccuracyPolicy, DomainError
from app.models import AccuracyVersion, AuditLog, DisplaySettings, ProductionRequest, Run
from app.services.auth import AuthService
from app.services.auth_types import AuthError
from app.services.production.base import stamp_update
from app.services.production.display_settings import DisplaySettingsService
from tests.auth_fixtures import invite_login
from tests.production_fixtures import SAMPLE, build_case, request_id
from tests.test_display_migration import production_rows


@pytest.mark.parametrize(
    "group,value,places,mode,expected",
    [
        ("resistance", "102.004", 2, "half_up", "102.00"),
        ("thickness", "0.007", 2, "half_up", "0.01"),
        ("speed", "12.25", 1, "half_up", "12.3"),
        ("length", "12.25", 1, "half_even", "12.2"),
        ("length", Decimal("1.25"), 1, "half_up", "1.3"),
        ("result", "12.50", 0, "half_even", "12"),
        ("resistance", "1.2", 6, "half_up", "1.200000"),
        ("resistance", "-0.004", 2, "half_up", "0.00"),
        ("result", str(MAX_RESULT), 0, "half_up", "1000000000000000000"),
    ],
)
def test_display_rounding(group, value, places, mode, expected) -> None:
    """Round only the presentation boundary, including halfway values and numeric carries."""
    formatter = DisplayFormatter(
        replace(AccuracyPolicy(), **{f"{group}_places": places}, rounding=mode)
    )
    with localcontext() as context:
        context.prec = 3
        assert formatter.format(value, group) == expected
        assert context.prec == 3


@pytest.mark.parametrize("value", [1.2, True, "NaN", "Infinity", "bad", "1e30", "1" * 65])
def test_display_invalid_values(value) -> None:
    """Reject invalid/nonfinite data and implicit float conversion in shared presentation."""
    with pytest.raises(DomainError, match="invalid_display_value"):
        DisplayFormatter(AccuracyPolicy()).format(value, "resistance")


def test_display_project_preserves_null_and_source() -> None:
    """Keep absence distinct from a displayed zero, without mutating canonical input values."""
    values = dict(SAMPLE, thickness=None, point_1="0.00", id=7)
    result = DisplayFormatter(AccuracyPolicy()).project(values, MEASUREMENT_QUANTITIES)
    assert result["thickness"] is None and result["point_1"] == "0.00"
    assert "id" not in result and values["id"] == 7
    assert values["thickness"] is None and values["point_1"] == "0.00"


def canonical(document: dict) -> dict:
    """Detach the display additions to compare all canonical history before and after changes."""
    data = json.loads(json.dumps(document))
    data.pop("display")
    for row in data["measurements"]:
        row.pop("display")
    return data


def assert_display_preserves_history(auth: AuthService, state: str) -> None:
    """Exercise real services on either database and retain all run/measurement/audit history."""
    case = build_case(auth)
    recording = replace(AccuracyPolicy(), resistance_places=3)
    case.settings.update(case.admin.token, request_id(), 1, recording, True, "Instrument accuracy")
    display = DisplaySettingsService(auth)
    assert display.get(case.admin.token).as_dict()["precision"]["resistance_places"] == 2
    run = case.start()
    sample = case.sample(run, point_1="101.005" if state == "active" else "102.004")
    if state in {"pending_review", "reviewed"}:
        closed = case.runs.close(
            case.admin.token, request_id(), run.id, sample.as_dict()["run_revision"]
        )
        if state == "reviewed":
            case.reviews.review(
                case.admin.token,
                request_id(),
                run.id,
                closed.revision,
                "confirmed_abnormal",
                "Checked",
            )
    if state == "legacy":
        with auth.factory.begin() as db:
            db.add(
                AccuracyVersion(
                    id=1,
                    **asdict(recording),
                    calculation_version="legacy",
                    created_at=auth.clock.now(),
                )
            )
            db.flush()
            legacy = db.get(Run, run.id)
            legacy.accuracy_version_id = 1
            stamp_update(legacy, auth.clock.now())
    before = canonical(case.runs.get_run(case.admin.token, run.id).as_dict())
    stored_before = production_rows(auth.factory.kw["bind"])
    with auth.factory() as db:
        audits = [
            (a.id, a.before_value, a.after_value, a.reason)
            for a in db.scalars(select(AuditLog).order_by(AuditLog.id))
        ]
    preference = replace(AccuracyPolicy(), resistance_places=0, thickness_places=2, result_places=0)
    updated = display.update(case.admin.token, request_id(), 1, preference, "Simpler display")
    after = case.runs.get_run(case.admin.token, run.id).as_dict()
    assert canonical(after) == before
    assert production_rows(auth.factory.kw["bind"]) == stored_before
    assert after["display"]["settings"]["revision"] == updated.revision
    assert after["measurements"][0]["display"]["thickness"] == "0.01"
    assert after["measurements"][0]["display"]["point_1"] == ("101" if state == "active" else "102")
    assert after["measurements"][0]["point_1"] == ("101.005" if state == "active" else "102.004")
    assert after["measurements"][0]["alarm_codes"] == before["measurements"][0]["alarm_codes"]
    assert after["rules"] == before["rules"] and after["accuracy"] == before["accuracy"]
    with auth.factory() as db:
        assert [
            (a.id, a.before_value, a.after_value, a.reason)
            for a in db.scalars(
                select(AuditLog).where(AuditLog.id <= audits[-1][0]).order_by(AuditLog.id)
            )
        ] == audits
    # New runs use the same current presentation while their recording accuracy stays separate.
    fresh = case.start()
    assert (
        case.runs.get_run(case.admin.token, fresh.id).as_dict()["display"]["settings"]["revision"]
        == updated.revision
    )
    assert fresh.as_dict()["accuracy"]["resistance_places"] == 3
    if state in {"active", "abnormal"}:
        corrected = case.measurements.save(
            case.admin.token,
            request_id(),
            run.id,
            sample.as_dict()["run_revision"],
            run.as_dict()["start_time"],
            dict(SAMPLE, point_1="101.005"),
            measurement_id=sample.id,
            expected_revision=sample.revision,
            slot_index=0,
            reason="Exact correction",
        )
        assert corrected.as_dict()["point_1"] == "101.005"


@pytest.mark.parametrize("state", ["active", "abnormal", "pending_review", "reviewed", "legacy"])
def test_display_changes_all_run_states_without_rewriting(auth: AuthService, state: str) -> None:
    """Apply current display settings across existing run states while preserving canonical data."""
    assert_display_preserves_history(auth, state)


@pytest.mark.parametrize("role", ["operator", "reviewer"])
def test_display_read_allowed_write_denied_and_idle_timeout(auth: AuthService, role: str) -> None:
    """All permitted viewers can format screens; only Admin can change factory presentation."""
    case = build_case(auth)
    _, user = invite_login(auth, case.admin, role)
    service = DisplaySettingsService(auth)
    assert service.get(user.token).revision == 1
    with pytest.raises(AuthError, match="permission_denied"):
        service.update(user.token, request_id(), 1, AccuracyPolicy(), "Not authorized")
    auth.clock.advance(auth.settings.session_idle_seconds - 1)
    service.get(user.token)
    auth.clock.advance(1)
    with pytest.raises(AuthError, match="authentication_required"):
        service.get(user.token)


def test_display_audit_retries_revisions_and_reasons(auth: AuthService) -> None:
    """Audit display edits and replay receipts without overwriting newer preferences."""
    case = build_case(auth)
    service = DisplaySettingsService(auth)
    preference = replace(AccuracyPolicy(), rounding="half_even", thickness_places=0)
    key = request_id()
    first = service.update(case.admin.token, key, 1, preference, "Readability")
    assert service.update(case.admin.token, key, 1, preference, "Readability") == first
    latest = service.update(case.admin.token, request_id(), 2, AccuracyPolicy(), "Restore")
    assert service.update(case.admin.token, key, 1, preference, "Readability") == first
    assert service.get(case.admin.token) == latest
    with pytest.raises(DomainError, match="request_conflict"):
        service.update(case.admin.token, key, 1, AccuracyPolicy(), "Readability")
    with pytest.raises(DomainError, match="revision_conflict"):
        service.update(case.admin.token, request_id(), 1, preference, "Stale")
    with pytest.raises(DomainError, match="reason_required"):
        service.update(case.admin.token, request_id(), latest.revision, preference, " ")
    with auth.factory() as db:
        rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "display_settings_changed")
                .order_by(AuditLog.id)
            )
        )
        assert len(rows) == 2
        assert rows[0].actor_id == case.admin.user.id and rows[0].reason == "Readability"
        assert json.loads(rows[0].before_value)["precision"]["thickness_places"] == 3
        assert json.loads(rows[0].after_value)["precision"]["thickness_places"] == 0


def test_display_audit_failure_rolls_back(auth: AuthService) -> None:
    """A failed audit cannot leave a changed display setting or a successful retry receipt."""
    case = build_case(auth)
    service = DisplaySettingsService(auth)
    before = service.get(case.admin.token)
    engine, key = auth.factory.kw["bind"], request_id()

    def fail(conn, cursor, statement, parameters, context, executemany) -> None:
        """Fail the real audit insertion within the shared database transaction."""
        if "INSERT INTO audit_logs" in statement:
            raise RuntimeError("display audit failed")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="display audit failed"):
            service.update(
                case.admin.token, key, 1, replace(AccuracyPolicy(), thickness_places=0), "Change"
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert service.get(case.admin.token) == before
    with auth.factory() as db:
        assert db.get(ProductionRequest, (case.admin.user.id, key)) is None


def test_missing_display_settings_fail_closed(auth: AuthService) -> None:
    """A missing settings seed produces an explicit service failure instead of guessed rounding."""
    case = build_case(auth)
    with auth.factory.begin() as db:
        db.delete(db.get(DisplaySettings, 1))
    with pytest.raises(DomainError, match="display_settings_unavailable"):
        DisplaySettingsService(auth).get(case.admin.token)


def test_admin_rounding_mode_changes_display_only(auth: AuthService) -> None:
    """An Admin can change halfway display results without changing entry accuracy or data."""
    case = build_case(auth)
    case.settings.update(
        case.admin.token,
        request_id(),
        1,
        replace(AccuracyPolicy(), resistance_places=3),
        True,
        "Three-place instrument",
    )
    run = case.start()
    case.sample(run, point_1="101.005")
    before = case.runs.get_run(case.admin.token, run.id).as_dict()
    assert before["measurements"][0]["display"]["point_1"] == "101.01"
    DisplaySettingsService(auth).update(
        case.admin.token,
        request_id(),
        1,
        replace(AccuracyPolicy(), rounding="half_even"),
        "Half-even display",
    )
    after = case.runs.get_run(case.admin.token, run.id).as_dict()
    assert after["measurements"][0]["display"]["point_1"] == "101.00"
    assert canonical(before) == canonical(after)

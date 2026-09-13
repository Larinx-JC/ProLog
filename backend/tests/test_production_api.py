"""HTTP acceptance for production lifecycle, exact values, ownership, retries and error paths."""

from dataclasses import asdict
from datetime import datetime

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from app.api.production_limits import MAX_BODY_BYTES
from app.domain.numeric import AccuracyPolicy
from app.models import AuditLog, Measurement, Run, User
from app.services.auth import AuthService
from tests.auth_fixtures import PASSWORD, invite_login
from tests.production_api_fixtures import ProductionBrowser, make_browser
from tests.production_fixtures import MATERIAL_RULES, SAMPLE, request_id


@pytest.fixture
def browser(auth: AuthService):
    """Provide the reusable real HTTP harness over fresh foreign-key-enforced storage."""
    result = make_browser(auth)
    with result.client:
        yield result


def test_http_full_lifecycle_and_terminal_immutability(browser: ProductionBrowser) -> None:
    """Record, correct, close and self-review over HTTP; final production cannot be edited."""
    run = browser.start()
    sample = browser.sample(run, point_1="103.00")
    assert sample["run_status"] == "abnormal"
    correction = dict(
        request_id=request_id(),
        expected_run_revision=sample["run_revision"],
        expected_revision=sample["revision"],
        measurement_time=run["start_time"],
        slot_index=0,
        values=SAMPLE,
        reason="Correct transcription",
    )
    path = f"/runs/{run['id']}/measurements/{sample['id']}"
    corrected = browser.write(path, correction, "PUT")
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["run_status"] == "abnormal"
    assert corrected.json()["status"] == "completed"
    closing = dict(request_id=request_id(), expected_revision=corrected.json()["run_revision"])
    closed = browser.write(f"/runs/{run['id']}/close", closing)
    assert closed.status_code == 200, closed.text
    assert closed.json()["pending_from"] == "abnormal"
    review = dict(
        request_id=request_id(),
        expected_revision=closed.json()["revision"],
        resolution="false_alarm",
        reason="Checked corrected entry",
    )
    final = browser.write(f"/runs/{run['id']}/review", review)
    assert final.status_code == 200 and final.json()["self_review"] is True
    assert browser.write(f"/runs/{run['id']}/review", review).json() == final.json()
    assert browser.write(f"/runs/{run['id']}/close", closing).json() == closed.json()
    rejected = browser.write(
        path,
        dict(correction, request_id=request_id(), expected_run_revision=final.json()["revision"]),
        "PUT",
    )
    assert rejected.status_code == 409 and rejected.json()["detail"] == "run_not_editable"
    with browser.case.auth.factory() as db:
        assert (
            db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "run_reviewed")) == 1
        )


def test_partial_missing_closure_and_required_reason(browser: ProductionBrowser) -> None:
    """A data gap requires an Admin explanation and remains visible after review."""
    run = browser.start()
    sample = browser.sample(run, point_2=None, thickness=None)
    assert sample["status"] == "missing" and sample["average_value"] is None
    payload = dict(request_id=request_id(), expected_revision=sample["run_revision"])
    result = browser.write(f"/runs/{run['id']}/close", payload)
    assert (
        result.status_code == 422 and result.json()["detail"] == "closure_exception_reason_required"
    )
    closed = browser.write(
        f"/runs/{run['id']}/close", dict(payload, exception_reason="Lost reading")
    )
    assert closed.status_code == 200 and closed.json()["missing_count_at_close"] == 1
    decision = dict(
        request_id=request_id(),
        expected_revision=closed.json()["revision"],
        resolution="approved",
        reason="Reviewed documented gap",
    )
    result = browser.write(f"/runs/{run['id']}/review", decision)
    assert result.status_code == 200 and result.json()["closure_exception_reason"] == "Lost reading"


READ_PATHS = [
    "/runs",
    "/runs/1",
    "/runs/1/measurements",
    "/runs/1/schedule",
    "/materials",
    "/materials/1",
    "/settings/accuracy",
    "/settings/display",
    "/audit-logs",
    "/overview",
]


@pytest.mark.parametrize("path", READ_PATHS)
def test_anonymous_production_reads_fail(browser: ProductionBrowser, path: str) -> None:
    """Every production GET denies missing authentication, including settings and aggregates."""
    browser.client.cookies.clear()
    response = browser.client.get("/production" + path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("role", ["operator", "reviewer"])
def test_role_access_and_direct_mutation_bypass(browser: ProductionBrowser, role: str) -> None:
    """Roles can read production, but cannot call Admin writes or another owner's mutations."""
    run = browser.start()
    sample = browser.sample(run)
    auth = browser.case.auth
    _, actor = invite_login(auth, browser.case.admin, role)
    browser.client.cookies.set(auth.settings.session_cookie, actor.token)
    for path in ("/runs", f"/runs/{run['id']}", "/materials", "/settings/display", "/overview"):
        assert browser.client.get("/production" + path).status_code == 200
    assert browser.client.get("/production/settings/accuracy").status_code == 403
    assert browser.client.get("/production/audit-logs").status_code == (
        200 if role == "reviewer" else 403
    )
    writes = [
        (
            "POST",
            "/materials",
            dict(request_id=request_id(), material_no="DENIED", rules=MATERIAL_RULES),
        ),
        (
            "PUT",
            f"/materials/{browser.case.material.id}",
            dict(
                request_id=request_id(),
                expected_revision=1,
                rules=MATERIAL_RULES,
                is_active=False,
                reason="Denied",
            ),
        ),
        (
            "PUT",
            "/settings/display",
            dict(
                request_id=request_id(),
                expected_revision=1,
                precision=asdict(AccuracyPolicy()),
                reason="Denied",
            ),
        ),
        (
            "PUT",
            "/settings/accuracy",
            dict(
                request_id=request_id(),
                expected_revision=1,
                accuracy=asdict(AccuracyPolicy()),
                operator_abnormal_allowed=False,
                reason="Denied",
            ),
        ),
        (
            "POST",
            f"/runs/{run['id']}/review",
            dict(
                request_id=request_id(), expected_revision=1, resolution="approved", reason="Denied"
            ),
        ),
        ("POST", f"/runs/{run['id']}/close", dict(request_id=request_id(), expected_revision=1)),
        (
            "POST",
            f"/runs/{run['id']}/measurements",
            dict(
                request_id=request_id(),
                expected_run_revision=1,
                measurement_time=run["start_time"],
                values=SAMPLE,
            ),
        ),
        (
            "PUT",
            f"/runs/{run['id']}/measurements/{sample['id']}",
            dict(
                request_id=request_id(),
                expected_run_revision=sample["run_revision"],
                expected_revision=sample["revision"],
                measurement_time=run["start_time"],
                values=SAMPLE,
                reason="Denied correction",
            ),
        ),
    ]
    for method, path, body in writes:
        assert browser.write(path, body, method).status_code == 403, path
    if role == "operator":
        owned = browser.start()
        sample = browser.sample(owned)
        assert (
            browser.write(
                f"/runs/{owned['id']}/close",
                dict(request_id=request_id(), expected_revision=sample["run_revision"]),
            ).status_code
            == 200
        )
    else:
        assert (
            browser.write(
                "/runs",
                dict(
                    request_id=request_id(),
                    material_id=1,
                    raw_material_batch="No",
                    interval_seconds=60,
                ),
            ).status_code
            == 403
        )


@pytest.mark.parametrize("case", ["missing", "wrong", "origin", "non-json"])
def test_production_csrf_rejections(browser: ProductionBrowser, case: str) -> None:
    """Actual production writes require the same browser proof and origin policy as auth."""
    proof = browser.proof()
    if case == "missing":
        proof.pop("X-CSRF-Token")
    elif case == "wrong":
        proof["X-CSRF-Token"] = "0" * 64
    elif case == "origin":
        proof["Origin"] = "https://evil.test"
    body = dict(
        request_id=request_id(), material_id=1, raw_material_batch="No", interval_seconds=60
    )
    response = browser.client.post(
        "/production/runs",
        headers=proof,
        **({"content": "{}"} if case == "non-json" else {"json": body}),
    )
    assert response.status_code == (415 if case == "non-json" else 403)
    with browser.case.auth.factory() as db:
        assert db.scalar(select(func.count(Run.id))) == 0


@pytest.mark.parametrize(
    "change",
    [
        dict(interval_seconds=True),
        dict(interval_seconds="60"),
        dict(interval_seconds=0),
        dict(material_id=1.0),
        dict(request_id="bad"),
        dict(created_by_id=1),
        dict(standard_value="100.00"),
    ],
)
def test_strict_run_requests(browser: ProductionBrowser, change: dict) -> None:
    """Reject coercion and caller-controlled identity/snapshot fields before any domain write."""
    body = dict(request_id=request_id(), material_id=1, raw_material_batch="B", interval_seconds=60)
    response = browser.write("/runs", body | change)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        dict(point_1=100.01),
        dict(point_1=True),
        dict(point_1="100.001"),
        dict(average_value="100"),
        dict(point_1="NaN"),
    ],
)
def test_exact_measurement_input_rejections(browser: ProductionBrowser, change: dict) -> None:
    """No floating input, nonfinite text, forged calculation or excess places reach storage."""
    run = browser.start()
    response = browser.write(
        f"/runs/{run['id']}/measurements",
        dict(
            request_id=request_id(),
            expected_run_revision=run["revision"],
            measurement_time=run["start_time"],
            values=SAMPLE | change,
        ),
    )
    assert response.status_code == 422
    with browser.case.auth.factory() as db:
        assert db.scalar(select(func.count(Measurement.id))) == 0


def test_http_settings_exact_display_and_material_edit_roundtrip(
    browser: ProductionBrowser,
) -> None:
    """Change both settings over HTTP while preserving canonical history and input policy."""
    changed = browser.write(
        "/settings/accuracy",
        dict(
            request_id=request_id(),
            expected_revision=1,
            accuracy=asdict(AccuracyPolicy(resistance_places=3)),
            operator_abnormal_allowed=True,
            reason="New instrument",
        ),
        "PUT",
    )
    assert changed.status_code == 200, changed.text
    run = browser.start()
    browser.sample(run, point_1="102.004")
    assert (
        browser.write(
            "/settings/display",
            dict(
                request_id=request_id(),
                expected_revision=1,
                precision=asdict(AccuracyPolicy(thickness_places=2)),
                reason="Display",
            ),
            "PUT",
        ).status_code
        == 200
    )
    result = browser.client.get(f"/production/runs/{run['id']}/measurements").json()
    item = result["items"][0]
    assert item["point_1"] == "102.004" and item["display"]["point_1"] == "102.00"
    assert item["thickness"] == "0.007" and item["display"]["thickness"] == "0.01"
    assert item["alarm_codes"] == ["point_1:target_deviation"]
    material = browser.client.get(f"/production/materials/{browser.case.material.id}").json()
    response = browser.write(
        f"/materials/{material['id']}",
        dict(
            request_id=request_id(),
            expected_revision=material["revision"],
            rules=material["rules"],
            is_active=True,
            reason="Unchanged exact rules",
        ),
        "PUT",
    )
    assert response.status_code == 200, response.text


def test_retries_stale_edits_and_cross_parent_correction(browser: ProductionBrowser) -> None:
    """Retry responses remain stable while stale revisions and mismatched parents reject."""
    payload = dict(
        request_id=request_id(), material_id=1, raw_material_batch="Retry", interval_seconds=60
    )
    first = browser.write("/runs", payload)
    assert first.json() == browser.write("/runs", payload).json()
    assert browser.write("/runs", payload | {"raw_material_batch": "Changed"}).status_code == 409
    run = first.json()
    sample = browser.sample(run)
    old = dict(
        request_id=request_id(),
        expected_run_revision=1,
        measurement_time=run["start_time"],
        values=SAMPLE,
    )
    assert browser.write(f"/runs/{run['id']}/measurements", old).status_code == 409
    another = browser.start()
    bad = old | dict(
        expected_run_revision=another["revision"],
        expected_revision=1,
        slot_index=0,
        reason="Wrong parent",
    )
    assert (
        browser.write(f"/runs/{another['id']}/measurements/{sample['id']}", bad, "PUT").status_code
        == 404
    )


def test_http_polling_expiry_revocation_and_forced_change(browser: ProductionBrowser) -> None:
    """Production reads do not renew idle time, and real session state controls each request."""
    run = browser.start()
    auth = browser.case.auth
    auth.clock.advance(1799)
    for path in READ_PATHS:
        assert browser.client.get("/production" + path).status_code == 200, path
    auth.clock.advance(1)
    assert browser.client.get("/production/runs").status_code == 401
    current = auth.login(browser.case.admin.user.account, PASSWORD, "fresh-client")
    browser.client.cookies.set(auth.settings.session_cookie, current.token)
    with auth.factory.begin() as db:
        db.get(User, current.user.id).must_change_password = True
    assert browser.client.get(f"/production/runs/{run['id']}").status_code == 403
    auth.logout(current.token)
    assert browser.client.get("/production/overview").status_code == 401


def test_http_audit_rollback_and_safe_database_error(browser: ProductionBrowser) -> None:
    """A database failure returns a sanitized 503 and rolls back production and audit changes."""
    run = browser.start()
    engine = browser.case.auth.factory.kw["bind"]

    def fail(conn, cursor, statement, parameters, context, executemany) -> None:
        """Fail the real audit insert after the sample/run writes were flushed."""
        if "INSERT INTO audit_logs" in statement:
            raise OperationalError("secret SQL", {}, Exception("secret connection"))

    event.listen(engine, "before_cursor_execute", fail)
    try:
        result = browser.write(
            f"/runs/{run['id']}/measurements",
            dict(
                request_id=request_id(),
                expected_run_revision=1,
                measurement_time=run["start_time"],
                values=SAMPLE,
            ),
        )
        assert result.status_code == 503 and result.json() == {"detail": "service_unavailable"}
        assert result.headers["cache-control"] == "no-store"
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with browser.case.auth.factory() as db:
        assert db.scalar(select(func.count(Measurement.id))) == 0
        assert db.get(Run, run["id"]).revision == 1


def test_overview_shanghai_midnight_and_empty_database(browser: ProductionBrowser) -> None:
    """Today's count uses the factory date while status counts include older open production."""
    assert browser.client.get("/production/overview").json()["total_runs"] == 0
    auth = browser.case.auth
    auth.clock.value = datetime(2026, 9, 7, 15, 59, 59)
    fresh = auth.login(browser.case.admin.user.account, PASSWORD, "midnight-test")
    browser.client.cookies.set(auth.settings.session_cookie, fresh.token)
    browser.start()
    auth.clock.advance(1)
    browser.start()
    result = browser.client.get("/production/overview").json()
    assert result["factory_date"] == "2026-09-08" and result["today_started_runs"] == 1
    assert result["total_runs"] == result["status_counts"]["active"] == 2
    assert result["recent_runs"][0]["id"] > result["recent_runs"][1]["id"]


def test_openapi_documents_decimal_strings_and_bounded_routes(browser: ProductionBrowser) -> None:
    """The actual API schema exposes required revision/UUID fields and decimal-string inputs."""
    spec = browser.client.get("/openapi.json").json()
    assert "/production/runs/{identifier}/measurements" in spec["paths"]
    reading = spec["components"]["schemas"]["ReadingInput"]["properties"]["point_1"]
    assert reading["anyOf"][0]["type"] == "string"
    assert spec["components"]["schemas"]["StartInput"]["additionalProperties"] is False
    assert "expected_revision" in spec["components"]["schemas"]["CorrectionInput"]["required"]
    pending = spec["components"]["schemas"]["RunOut"]["properties"]["pending_from"]
    assert pending["anyOf"][0]["enum"] == ["active", "abnormal"]


def test_every_write_denies_preauth_cookie(browser: ProductionBrowser) -> None:
    """A valid anonymous CSRF proof cannot authorize any production mutation."""
    run = browser.start()
    sample = browser.sample(run)
    browser.client.cookies.clear()
    common = dict(request_id=request_id(), expected_revision=1, reason="Unauthorized")
    reading = dict(
        request_id=request_id(),
        expected_run_revision=sample["run_revision"],
        measurement_time=run["start_time"],
        values=SAMPLE,
    )
    cases = [
        (
            "POST",
            "/runs",
            dict(
                request_id=request_id(),
                material_id=1,
                raw_material_batch="Unauthorized",
                interval_seconds=60,
            ),
        ),
        ("POST", f"/runs/{run['id']}/measurements", reading),
        ("PUT", f"/runs/{run['id']}/measurements/{sample['id']}", reading | common),
        ("POST", f"/runs/{run['id']}/close", dict(request_id=request_id(), expected_revision=2)),
        ("POST", f"/runs/{run['id']}/review", common | dict(resolution="approved")),
        (
            "POST",
            "/materials",
            dict(request_id=request_id(), material_no="Denied", rules=MATERIAL_RULES),
        ),
        ("PUT", "/materials/1", common | dict(rules=MATERIAL_RULES, is_active=False)),
        (
            "PUT",
            "/settings/accuracy",
            common | dict(accuracy=asdict(AccuracyPolicy()), operator_abnormal_allowed=False),
        ),
        ("PUT", "/settings/display", common | dict(precision=asdict(AccuracyPolicy()))),
    ]
    for method, path, body in cases:
        response = browser.write(path, body, method)
        assert response.status_code == 401, (path, response.text)
    with browser.case.auth.factory() as db:
        assert db.scalar(select(func.count(Run.id))) == 1
        assert db.get(Run, run["id"]).revision == 2
        assert db.scalar(select(func.count(Measurement.id))) == 1


def test_http_body_limit_applies_before_json_parsing(browser: ProductionBrowser) -> None:
    """The registered middleware rejects oversized malformed JSON without reflecting it."""
    response = browser.client.post(
        "/production/runs",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers=browser.proof() | {"Content-Type": "application/json"},
    )
    assert response.status_code == 413 and response.json() == {"detail": "request_too_large"}
    assert response.headers["cache-control"] == "no-store"
    with browser.case.auth.factory() as db:
        assert db.scalar(select(func.count(Run.id))) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"thickness_places": True},
        {"thickness_places": "3"},
        {"thickness_places": 7},
        {"rounding": "truncate"},
        {"unexpected": 2},
    ],
)
def test_settings_reject_coerced_or_partial_policy(
    browser: ProductionBrowser, change: dict
) -> None:
    """Invalid or incomplete nested policies cannot reset settings or increment revision."""
    body = dict(request_id=request_id(), expected_revision=1, reason="Invalid settings")
    for precision in (asdict(AccuracyPolicy()) | change, {"resistance_places": 2}):
        result = browser.write("/settings/display", body | dict(precision=precision), "PUT")
        assert result.status_code == 422
    assert browser.client.get("/production/settings/display").json()["revision"] == 1

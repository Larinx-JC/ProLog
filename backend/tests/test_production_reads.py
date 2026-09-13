"""Bounded read behavior, stable pagination, exact inactive standards and original audit data."""

from dataclasses import asdict
from decimal import Decimal

import pytest
from sqlalchemy import event, select

from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import AccuracyVersion, AuditLog, Measurement, MeasurementStatus, Run
from app.services.auth import AuthService
from app.services.production.reads import ProductionReadService, exact_material_value, validate_page
from tests.production_api_fixtures import ProductionBrowser, make_browser
from tests.production_fixtures import MATERIAL_RULES, request_id


@pytest.fixture
def browser(auth: AuthService):
    """Use actual routes and a dedicated database to observe materialized rows."""
    value = make_browser(auth)
    with value.client:
        yield value


@pytest.mark.parametrize("offset,limit", [(-1, 50), (True, 50), (0, 0), (0, 201), (0, True)])
def test_service_page_bounds_cannot_be_bypassed(offset, limit) -> None:
    """The underlying service rejects invalid limits even without HTTP validation."""
    with pytest.raises(DomainError, match="invalid_page"):
        validate_page(offset, limit)


@pytest.mark.parametrize(
    "value,expected",
    [("100", "100"), ("100.000000", "100"), ("0.000000", "0"), ("0.006000", "0.006")],
)
def test_material_padding_removal_is_exact(value: str, expected: str) -> None:
    """Canonical material transport strips padding only, never significant digits."""
    assert exact_material_value(Decimal(value)) == expected


def test_detail_does_not_materialize_samples_and_pages_are_parent_scoped(
    browser: ProductionBrowser,
) -> None:
    """Observe ORM loads to prove pagination limits query materialization, not just JSON size."""
    first, second = browser.start(), browser.start()
    auth = browser.case.auth
    with auth.factory.begin() as db:
        # Test-volume setup only: production writers never insert arbitrary ORM rows.
        db.add_all(
            [
                Measurement(
                    run_id=first["id"],
                    measurement_time=auth.clock.now(),
                    point_1=Decimal("100.00"),
                    status=MeasurementStatus.MISSING,
                )
                for _ in range(205)
            ]
        )
        db.add(Measurement(run_id=second["id"], measurement_time=auth.clock.now()))
    loaded = []

    def observe(row, context) -> None:
        """Count actual measurement ORM loads while HTTP reads execute."""
        loaded.append(row.id)

    event.listen(Measurement, "load", observe)
    try:
        detail = browser.client.get(f"/production/runs/{first['id']}")
        assert detail.status_code == 200 and detail.json()["measurement_count"] == 205
        assert "measurements" not in detail.json() and loaded == []
        initial = browser.client.get(
            f"/production/runs/{first['id']}/measurements?limit=200"
        ).json()
        assert len(initial["items"]) == len(loaded) == 200
        assert initial["total"] == 205 and initial["has_more"]
        final = browser.client.get(
            f"/production/runs/{first['id']}/measurements?offset=200&limit=200"
        ).json()
        assert len(final["items"]) == 5 and not final["has_more"]
        ids = [r["id"] for r in initial["items"] + final["items"]]
        assert ids == sorted(set(ids))
        assert {r["run_id"] for r in final["items"]} == {first["id"]}
        empty = browser.client.get(f"/production/runs/{first['id']}/measurements?offset=500").json()
        assert empty["total"] == 205 and empty["items"] == [] and not empty["has_more"]
    finally:
        event.remove(Measurement, "load", observe)
    page = browser.client.get("/production/runs?limit=1").json()
    assert page["total"] == 2 and page["items"][0]["id"] == second["id"]
    assert (
        browser.client.get("/production/runs?offset=1&limit=1").json()["items"][0]["id"]
        == first["id"]
    )


@pytest.mark.parametrize(
    "path", ["/runs/99999", "/runs/99999/measurements", "/materials/99999", "/runs/99999/schedule"]
)
def test_missing_read_targets(browser: ProductionBrowser, path: str) -> None:
    """Missing parents fail explicitly instead of returning unrelated or fabricated records."""
    assert browser.client.get("/production" + path).status_code == 404


@pytest.mark.parametrize("query", ["limit=201", "limit=0", "offset=-1", "limit=true"])
def test_http_page_constraints(browser: ProductionBrowser, query: str) -> None:
    """Public page parameters reject invalid values before reaching storage."""
    for path in ("runs", "materials", "audit-logs", "runs/1/measurements", "runs/1/schedule"):
        assert browser.client.get(f"/production/{path}?{query}").status_code == 422


def test_inactive_materials_preserve_old_precision_and_audits(browser: ProductionBrowser) -> None:
    """Lower recording precision cannot round archived standards or historical audit payloads."""
    created = browser.write(
        "/materials", dict(request_id=request_id(), material_no="SECOND", rules=MATERIAL_RULES)
    )
    assert created.status_code == 201
    for identifier in (browser.case.material.id, created.json()["id"]):
        result = browser.write(
            f"/materials/{identifier}",
            dict(
                request_id=request_id(),
                expected_revision=1,
                rules=MATERIAL_RULES,
                is_active=False,
                reason="Archived",
            ),
            "PUT",
        )
        assert result.status_code == 200
    updated = browser.write(
        "/settings/accuracy",
        dict(
            request_id=request_id(),
            expected_revision=1,
            accuracy=asdict(AccuracyPolicy(thickness_places=2)),
            operator_abnormal_allowed=True,
            reason="Coarser new input",
        ),
        "PUT",
    )
    assert updated.status_code == 200
    materials = browser.client.get("/production/materials?limit=1").json()
    assert materials["total"] == 2 and materials["has_more"]
    assert materials["items"][0]["rules"]["thickness_min"] == "0.006"
    latest = browser.client.get("/production/audit-logs?limit=1").json()
    assert latest["has_more"] and latest["items"][0]["action"] == "production_settings_changed"
    with browser.case.auth.factory() as db:
        row = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        assert latest["items"][0]["after_value"] == row.after_value
    assert browser.case.admin.token not in str(latest)


def test_legacy_read_does_not_invent_scheduled_completeness(browser: ProductionBrowser) -> None:
    """The bounded API preserves the approved read-only legacy semantics."""
    run = browser.start()
    auth = browser.case.auth
    with auth.factory.begin() as db:
        db.add(
            AccuracyVersion(
                id=1,
                **asdict(AccuracyPolicy()),
                calculation_version="legacy",
                created_at=auth.clock.now(),
            )
        )
        db.flush()
        db.get(Run, run["id"]).accuracy_version_id = 1
    result = browser.client.get(f"/production/runs/{run['id']}")
    assert result.status_code == 200 and result.json()["missing_count"] is None
    assert browser.client.get(f"/production/runs/{run['id']}/schedule").status_code == 409
    assert (
        ProductionReadService(auth).runs(browser.case.admin.token, 999, 1).as_dict()["items"] == []
    )

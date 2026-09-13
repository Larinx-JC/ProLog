"""Real HTTP requests against migrated MySQL exercise production transport and transactions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.domain.numeric import AccuracyPolicy
from app.models import Measurement, Run
from app.services.auth import AuthService
from tests.auth_fixtures import invite_login
from tests.production_api_fixtures import make_browser
from tests.production_fixtures import SAMPLE, request_id

pytestmark = pytest.mark.mysql


def test_mysql_http_exact_values_review_and_permissions(mysql_auth: AuthService) -> None:
    """MySQL preserves six-place input through HTTP; completed review remains immutable."""
    browser = make_browser(mysql_auth)
    with browser.client:
        changed = browser.write(
            "/settings/accuracy",
            dict(
                request_id=request_id(),
                expected_revision=1,
                accuracy=asdict(AccuracyPolicy(resistance_places=6, thickness_places=6)),
                operator_abnormal_allowed=True,
                reason="Six-place input",
            ),
            "PUT",
        )
        assert changed.status_code == 200
        run = browser.start()
        sample = browser.sample(run, point_1="102.000001", thickness="0.006001")
        item = browser.client.get(f"/production/runs/{run['id']}/measurements").json()["items"][0]
        assert item["point_1"] == "102.000001" and item["thickness"] == "0.006001"
        assert item["status"] == "abnormal" and item["target_deviation_percent"] == "2.00"
        closed = browser.write(
            f"/runs/{run['id']}/close",
            dict(request_id=request_id(), expected_revision=sample["run_revision"]),
        )
        assert closed.status_code == 200
        final = browser.write(
            f"/runs/{run['id']}/review",
            dict(
                request_id=request_id(),
                expected_revision=closed.json()["revision"],
                resolution="confirmed_abnormal",
                reason="Checked",
            ),
        )
        assert final.status_code == 200
        _, reviewer = invite_login(mysql_auth, browser.case.admin, "reviewer")
        browser.client.cookies.set(mysql_auth.settings.session_cookie, reviewer.token)
        assert browser.client.get("/production/audit-logs").status_code == 200
        assert (
            browser.write(
                "/runs",
                dict(
                    request_id=request_id(),
                    material_id=1,
                    raw_material_batch="Denied",
                    interval_seconds=60,
                ),
            ).status_code
            == 403
        )


def test_mysql_http_concurrent_writes_have_one_revision_winner(mysql_auth: AuthService) -> None:
    """Separate HTTP clients and DB connections cannot overwrite the same run revision."""
    browser = make_browser(mysql_auth)
    with browser.client:
        run = browser.start()
        barrier = Barrier(2)

        def write() -> int:
            """Submit a distinct request through an independent browser and worker thread."""
            with TestClient(browser.client.app, base_url="https://testserver") as client:
                client.cookies.set(mysql_auth.settings.session_cookie, browser.case.admin.token)
                proof = client.get("/auth/csrf").json()["csrf_token"]
                barrier.wait(timeout=10)
                result = client.post(
                    f"/production/runs/{run['id']}/measurements",
                    json=dict(
                        request_id=request_id(),
                        expected_run_revision=1,
                        measurement_time=run["start_time"],
                        slot_index=0,
                        values=SAMPLE,
                    ),
                    headers={"Origin": mysql_auth.settings.public_url, "X-CSRF-Token": proof},
                )
                return result.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write) for _ in range(2)]
            assert sorted(f.result(timeout=30) for f in futures) == [201, 409]
        with mysql_auth.factory() as db:
            assert db.scalar(select(func.count(Measurement.id))) == 1
            assert db.get(Run, run["id"]).revision == 2

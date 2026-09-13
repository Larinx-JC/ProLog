"""Reusable HTTP production harness with real services and disposable authenticated sessions."""

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth import AuthService
from tests.production_fixtures import SAMPLE, ProductionCase, build_case, request_id


@dataclass
class ProductionBrowser:
    """Send real cookie/CSRF requests against the composed application."""

    case: ProductionCase
    client: TestClient

    def proof(self) -> dict[str, str]:
        """Get a cookie-bound CSRF proof after any test session change."""
        return {
            "Origin": self.case.auth.settings.public_url,
            "X-CSRF-Token": self.client.get("/auth/csrf").json()["csrf_token"],
        }

    def write(self, path: str, data: dict, method: str = "POST"):
        """Exercise the actual JSON/Origin/CSRF middleware and typed route."""
        return self.client.request(method, "/production" + path, json=data, headers=self.proof())

    def start(self) -> dict:
        """Create a run through HTTP and assert transport-level success."""
        response = self.write(
            "/runs",
            dict(
                request_id=request_id(),
                material_id=self.case.material.id,
                raw_material_batch="B-HTTP",
                interval_seconds=60,
            ),
        )
        assert response.status_code == 201, response.text
        return response.json()

    def sample(self, run: dict, **changes) -> dict:
        """Record the start-slot sample using returned server time and revision."""
        response = self.write(
            f"/runs/{run['id']}/measurements",
            dict(
                request_id=request_id(),
                expected_run_revision=run["revision"],
                measurement_time=run["start_time"],
                slot_index=0,
                values=dict(SAMPLE, **changes),
            ),
        )
        assert response.status_code == 201, response.text
        return response.json()


def make_browser(auth: AuthService) -> ProductionBrowser:
    """Bind an injectable real database service to the actual FastAPI application."""
    case = build_case(auth)
    app = create_app()
    app.state.auth = auth
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(auth.settings.session_cookie, case.admin.token)
    return ProductionBrowser(case, client)

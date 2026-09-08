"""Browser transport acceptance: cookies, CSRF, errors and direct API permissions."""

from typing import Annotated
from urllib.parse import urlsplit

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.auth import require_permission
from app.main import create_app
from app.models import User
from app.services.auth import AuthService
from app.services.auth_types import Identity, Permission
from tests.auth_fixtures import PASSWORD, REPLACEMENT, bootstrap_login


@pytest.fixture
def browser(auth: AuthService):
    """Use the actual FastAPI middleware/routes with a disposable auth service."""
    app = create_app()
    app.state.auth = auth

    @app.get("/test/read")
    def protected(
        identity: Annotated[Identity, Depends(require_permission(Permission.RUN_READ))],
    ) -> dict:
        """Demonstrate the shared dependency without implementing Section 5 endpoints."""
        return {"id": identity.id}

    with TestClient(app, base_url="https://testserver") as client:
        yield client


def headers(browser: TestClient, auth: AuthService) -> dict[str, str]:
    """Get a fresh cookie-bound proof, as the browser shell will do in Section 9."""
    return {
        "Origin": auth.settings.public_url,
        "X-CSRF-Token": browser.get("/auth/csrf").json()["csrf_token"],
    }


def login(browser: TestClient, auth: AuthService) -> dict:
    """Bootstrap and sign in through the actual JSON/cookie login route."""
    auth.bootstrap("admin.test", "Admin", PASSWORD)
    response = browser.post(
        "/auth/login",
        json={"account": "admin.test", "password": PASSWORD},
        headers=headers(browser, auth),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_cookies_and_safe_current_user(browser: TestClient, auth: AuthService) -> None:
    """A login issues HttpOnly cookies and safe JSON with no stored hash/token."""
    result = login(browser, auth)
    response = browser.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["id"] == result["user"]["id"]
    assert "password_hash" not in response.text and "token_digest" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert browser.get("/test/read").status_code == 200
    cookie = next(c for c in browser.cookies.jar if c.name == auth.settings.session_cookie)
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.get_nonstandard_attr("SameSite") == "strict"


@pytest.mark.parametrize("case", ["absent", "wrong", "foreign-origin", "null-origin", "non-json"])
def test_csrf_and_origin_rejections(browser: TestClient, auth: AuthService, case: str) -> None:
    """State changes require both an allowed origin and a valid browser proof."""
    auth.bootstrap("admin.test", "Admin", PASSWORD)
    proof = headers(browser, auth)
    if case == "absent":
        proof.pop("X-CSRF-Token")
    elif case == "wrong":
        proof["X-CSRF-Token"] = "0" * 64
    elif case in {"foreign-origin", "null-origin"}:
        proof["Origin"] = "https://evil.test" if case == "foreign-origin" else "null"
    if case == "non-json":
        response = browser.post("/auth/logout", content="{}", headers=proof)
        assert response.status_code == 415
    else:
        response = browser.post(
            "/auth/login", json={"account": "admin.test", "password": PASSWORD}, headers=proof
        )
        assert response.status_code == 403
    assert auth.settings.session_cookie not in browser.cookies


def test_cookie_fixation_and_csrf_rotation(browser: TestClient, auth: AuthService) -> None:
    """A caller-selected cookie never becomes the new authenticated credential."""
    browser.cookies.set(
        auth.settings.session_cookie, "caller-selected", domain="testserver.local", path="/"
    )
    result = login(browser, auth)
    assert browser.cookies.get(auth.settings.session_cookie) != "caller-selected"
    assert result["csrf_token"] != auth.tokens.keyed_digest("csrf", "caller-selected")


def test_invalid_password_response_does_not_echo_secrets(
    browser: TestClient, auth: AuthService
) -> None:
    """Validation errors omit the submitted credential rather than reflecting input."""
    secret = "secret-too-short"
    response = browser.post(
        "/auth/activate",
        json={"token": secret, "password": "tiny-secret"},
        headers=headers(browser, auth),
    )
    assert response.status_code == 422
    assert secret not in response.text and "tiny-secret" not in response.text
    assert "input" not in response.text


def test_api_invitation_activation_recovery_and_account_management(
    browser: TestClient, auth: AuthService
) -> None:
    """Exercise the complete account flow through real routes and cookies."""
    login(browser, auth)
    response = browser.post(
        "/auth/users",
        json={"account": "operator.test", "name": "Operator", "role": "operator"},
        headers=headers(browser, auth),
    )
    assert response.status_code == 201
    grant = response.json()
    token = urlsplit(grant["url"]).fragment.removeprefix("token=")
    response = browser.post(
        "/auth/activate",
        json={"token": token, "password": PASSWORD},
        headers=headers(browser, auth),
    )
    assert response.status_code == 200
    user_id = response.json()["id"]
    assert len(browser.get("/auth/users").json()) == 2
    response = browser.post(
        f"/auth/users/{user_id}/grants/recovery", json={}, headers=headers(browser, auth)
    )
    token = urlsplit(response.json()["url"]).fragment.removeprefix("token=")
    assert (
        browser.post(
            "/auth/recover",
            json={"token": token, "password": REPLACEMENT},
            headers=headers(browser, auth),
        ).status_code
        == 200
    )
    response = browser.patch(
        f"/auth/users/{user_id}", json={"is_active": False}, headers=headers(browser, auth)
    )
    assert response.status_code == 200 and not response.json()["is_active"]


def test_api_expiry_activity_logout_and_password_change(
    browser: TestClient, auth: AuthService
) -> None:
    """Explicit activity renews idle time; password change revokes the browser session."""
    login(browser, auth)
    auth.clock.advance(1700)
    assert (
        browser.post("/auth/activity", json={}, headers=headers(browser, auth)).status_code == 200
    )
    auth.clock.advance(200)
    assert browser.get("/auth/me").status_code == 200
    response = browser.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": REPLACEMENT},
        headers=headers(browser, auth),
    )
    assert response.status_code == 200
    assert browser.get("/auth/me").status_code == 401
    assert browser.post("/auth/logout", json={}, headers=headers(browser, auth)).status_code == 200


def test_get_cannot_activate_or_log_out(browser: TestClient, auth: AuthService) -> None:
    """GET account mutation routes are unavailable and leave the session usable."""
    login(browser, auth)
    for path in ["/auth/activate", "/auth/recover", "/auth/logout", "/auth/password"]:
        assert browser.get(path).status_code == 405
    assert browser.get("/auth/me").status_code == 200


def test_api_rate_limit_and_database_failure(
    browser: TestClient, auth: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Throttling is explicit and database failure never returns account authority."""
    proof = headers(browser, auth)
    for _ in range(auth.settings.login_account_limit):
        assert (
            browser.post(
                "/auth/login", json={"account": "unknown", "password": "wrong"}, headers=proof
            ).status_code
            == 401
        )
    response = browser.post(
        "/auth/login", json={"account": "unknown", "password": "wrong"}, headers=proof
    )
    assert response.status_code == 429 and "Retry-After" in response.headers

    def broken(*args, **kwargs):
        """Simulate a database outage without connecting to an external service."""
        raise OperationalError("query", {}, Exception("unavailable"))

    monkeypatch.setattr(auth, "factory", broken)
    response = browser.get("/auth/me")
    assert response.status_code == 503 and response.json() == {"detail": "service_unavailable"}


def test_secure_cookie_prefix_in_production(browser: TestClient, auth: AuthService) -> None:
    """Production emits Secure host-only cookies with the required prefix and path."""
    auth.settings.secure_cookies = True
    auth.settings.public_url = "https://testserver"
    result = login(browser, auth)
    assert result["user"]["role"] == "admin"
    cookie = next(c for c in browser.cookies.jar if c.name == "__Host-prolog_session")
    assert cookie.secure and cookie.path == "/" and not cookie.domain_specified


@pytest.mark.parametrize("role", ["operator", "reviewer"])
def test_non_admin_cannot_call_user_api(browser: TestClient, auth: AuthService, role: str) -> None:
    """Direct API requests are denied even if someone bypasses future UI guards."""
    from tests.auth_fixtures import invite_login

    admin = bootstrap_login(auth)
    _, actor = invite_login(auth, admin, role)
    browser.cookies.set(auth.settings.session_cookie, actor.token)
    assert browser.get("/auth/users").status_code == 403
    assert (
        browser.post(
            "/auth/users",
            json={"account": "bypass", "name": "Bypass", "role": "admin"},
            headers=headers(browser, auth),
        ).status_code
        == 403
    )


def test_api_logout_clears_cookie_and_rejects_replay(
    browser: TestClient, auth: AuthService
) -> None:
    """Logout clears the browser cookie and invalidates the copied server credential."""
    login(browser, auth)
    token = browser.cookies.get(auth.settings.session_cookie)
    response = browser.post("/auth/logout", json={}, headers=headers(browser, auth))
    assert response.status_code == 200 and auth.settings.session_cookie not in browser.cookies
    browser.cookies.set(auth.settings.session_cookie, token)
    assert browser.get("/auth/me").status_code == 401
    assert browser.post("/auth/logout", json={}, headers=headers(browser, auth)).status_code == 200


def test_forced_change_restricts_actual_api_routes(browser: TestClient, auth: AuthService) -> None:
    """A forced-change account cannot call protected routes or renew idle time."""
    result = login(browser, auth)
    with auth.factory.begin() as db:
        db.get(User, result["user"]["id"]).must_change_password = True
    for path in ("/auth/me", "/auth/users", "/test/read"):
        assert browser.get(path).status_code == 403
    assert (
        browser.post("/auth/activity", json={}, headers=headers(browser, auth)).status_code == 403
    )
    response = browser.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": REPLACEMENT},
        headers=headers(browser, auth),
    )
    assert response.status_code == 200


def test_background_auth_reads_do_not_keep_session_alive(
    browser: TestClient, auth: AuthService
) -> None:
    """Current-account, Admin-list and CSRF refresh GETs leave the idle deadline fixed."""
    login(browser, auth)
    auth.clock.advance(auth.settings.session_idle_seconds - 1)
    for path in ("/auth/me", "/auth/users", "/auth/csrf"):
        assert browser.get(path).status_code == 200
    auth.clock.advance(1)
    assert browser.get("/auth/me").status_code == 401

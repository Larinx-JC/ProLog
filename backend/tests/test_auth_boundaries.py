"""Additional expiry, invalid-input and credential-upgrade regressions."""

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import User
from app.services.auth import AuthService
from app.services.auth_types import AuthError
from tests.auth_fixtures import PASSWORD, REPLACEMENT, bootstrap_login


@pytest.mark.parametrize("offset,accepted", [(-0.000001, True), (0, False), (1, False)])
def test_absolute_expiry_boundaries(auth: AuthService, offset: float, accepted: bool) -> None:
    """Absolute expiry rejects at/after its deadline despite recent foreground activity."""
    auth.settings.session_idle_seconds = 15
    auth.settings.session_max_seconds = 30
    admin = bootstrap_login(auth)
    auth.clock.advance(14)
    auth.current(admin.token, activity=True)
    auth.clock.advance(14)
    auth.current(admin.token, activity=True)
    auth.clock.advance(2 + offset)
    if accepted:
        assert auth.current(admin.token).id == admin.user.id
    else:
        with pytest.raises(AuthError):
            auth.current(admin.token, activity=True)


@pytest.mark.parametrize("offset,accepted", [(-0.000001, True), (0, False), (1, False)])
def test_recovery_expiry_boundaries(auth: AuthService, offset: float, accepted: bool) -> None:
    """The separate recovery lifetime is enforced at its exact deadline."""
    admin = bootstrap_login(auth)
    grant = auth.issue_grant(admin.token, admin.user.id, "recovery")
    auth.clock.advance(auth.settings.recovery_seconds + offset)
    if accepted:
        assert auth.consume_grant(grant.token, "recovery", REPLACEMENT, "client").is_active
    else:
        with pytest.raises(AuthError):
            auth.consume_grant(grant.token, "recovery", REPLACEMENT, "client")


def test_invalid_administration_leaves_accounts_unchanged(auth: AuthService) -> None:
    """Invalid roles, targets, grant types and pending-account enables fail atomically."""
    admin = bootstrap_login(auth)
    grant = auth.invite(admin.token, "pending.user", "Pending", "operator")
    operations = [
        lambda: auth.invite(admin.token, "bad.role", "Bad", "unknown"),
        lambda: auth.invite(admin.token, "bad.name", " ", "operator"),
        lambda: auth.change_user(admin.token, 999999, "operator", None),
        lambda: auth.change_user(admin.token, admin.user.id, None, None),
        lambda: auth.change_user(admin.token, grant.user.id, None, True),
        lambda: auth.issue_grant(admin.token, grant.user.id, "recovery"),
        lambda: auth.issue_grant(admin.token, grant.user.id, "invalid"),
        lambda: auth.issue_grant(admin.token, admin.user.id, "activation"),
        lambda: auth.list_users(admin.token, -1, 100),
    ]
    for operation in operations:
        with pytest.raises(AuthError):
            operation()
    with pytest.raises(AuthError, match="invalid_credentials"):
        auth.login("invalid account", PASSWORD, "client")
    with auth.factory() as db:
        assert db.scalar(select(func.count(User.id))) == 2


def test_older_argon2_hash_is_upgraded_at_successful_login(auth: AuthService) -> None:
    """Successful login upgrades old hash parameters while retaining the password."""
    admin = bootstrap_login(auth)
    old = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    with auth.factory.begin() as db:
        db.get(User, admin.user.id).password_hash = old
    auth.login(admin.user.account, PASSWORD, "client")
    with auth.factory() as db:
        encoded = db.get(User, admin.user.id).password_hash
        assert encoded != old and not auth.passwords.needs_rehash(encoded)


def test_invalid_account_value_is_sanitized(auth: AuthService) -> None:
    """Service-level input validation returns a safe error rather than reflected data."""
    admin = bootstrap_login(auth)
    app = create_app()
    app.state.auth = auth
    with TestClient(app) as browser:
        browser.cookies.set(auth.settings.session_cookie, admin.token)
        csrf = browser.get("/auth/csrf").json()["csrf_token"]
        response = browser.post(
            "/auth/users",
            json={"account": "bad account", "name": "Bad", "role": "operator"},
            headers={"Origin": auth.settings.public_url, "X-CSRF-Token": csrf},
        )
        assert response.status_code == 400 and response.json() == {"detail": "invalid_input"}

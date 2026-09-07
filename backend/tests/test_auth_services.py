"""Authentication acceptance tests covering state, authority, expiry and rollback."""

from dataclasses import replace

import pytest
from sqlalchemy import event, func, select

from app.models import AccessGrant, AuditLog, AuthState, LoginSession, User
from app.services.auth import AuthService
from app.services.auth_types import AuthError, Permission
from tests.auth_fixtures import PASSWORD, REPLACEMENT, bootstrap_login, invite_login


def test_bootstrap_once_and_normalized_duplicate(auth: AuthService) -> None:
    """Bootstrap is one-use; normalized duplicate invitations create no partial account."""
    admin = bootstrap_login(auth)
    with pytest.raises(AuthError, match="bootstrap_already_completed"):
        auth.bootstrap("another.admin", "Other", PASSWORD)
    with pytest.raises(AuthError, match="account_exists"):
        auth.invite(admin.token, " ADMIN.TEST ", "Duplicate", "operator")
    with auth.factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(AccessGrant.id))) == 0


def test_activation_and_login_never_store_or_repr_raw_tokens(auth: AuthService) -> None:
    """Activation creates a usable account; stored credentials and repr omit raw tokens."""
    admin = bootstrap_login(auth)
    grant, operator = invite_login(auth, admin)
    assert "#token=" in grant.url and "?" not in grant.url
    assert grant.token not in repr(grant) and operator.token not in repr(operator)
    assert operator.user.activated and not operator.user.must_change_password
    with auth.factory() as db:
        row = db.scalar(select(AccessGrant).where(AccessGrant.user_id == operator.user.id))
        assert row.consumed_at is not None and row.revoked_at is None
        assert row.token_digest == auth.tokens.digest(grant.token)
        logs = " ".join(str(vars(log)) for log in db.scalars(select(AuditLog)))
        assert PASSWORD not in logs and grant.token not in logs and operator.token not in logs
    with pytest.raises(AuthError, match="invalid_or_expired_link"):
        auth.consume_grant(grant.token, "activation", REPLACEMENT, "client")


@pytest.mark.parametrize("offset,accepted", [(-0.000001, True), (0, False), (1, False)])
def test_activation_expiry_boundary(auth: AuthService, offset: float, accepted: bool) -> None:
    """Expiry is inclusive: an activation link is invalid exactly at its deadline."""
    admin = bootstrap_login(auth)
    grant = auth.invite(admin.token, "operator.test", "Operator", "operator")
    auth.clock.advance(auth.settings.activation_seconds + offset)
    if accepted:
        assert auth.consume_grant(grant.token, "activation", PASSWORD, "client").activated
    else:
        with pytest.raises(AuthError, match="invalid_or_expired_link"):
            auth.consume_grant(grant.token, "activation", PASSWORD, "client")


def test_reissuing_and_disabling_revoke_grants(auth: AuthService) -> None:
    """Only the newest link works; disabling an invited user prevents its activation."""
    admin = bootstrap_login(auth)
    first = auth.invite(admin.token, "operator.test", "Operator", "operator")
    second = auth.issue_grant(admin.token, first.user.id, "activation")
    with pytest.raises(AuthError):
        auth.consume_grant(first.token, "activation", PASSWORD, "client")
    auth.change_user(admin.token, first.user.id, None, False)
    with pytest.raises(AuthError):
        auth.consume_grant(second.token, "activation", PASSWORD, "client")


@pytest.mark.parametrize("case", ["wrong", "unknown", "disabled", "pending", "unknown-role"])
def test_login_rejections_are_generic(auth: AuthService, case: str) -> None:
    """Different invalid account conditions share one public login rejection."""
    admin = bootstrap_login(auth)
    account, password = "operator.test", PASSWORD
    if case == "pending":
        auth.invite(admin.token, account, "Operator", "operator")
    elif case != "unknown":
        _, operator = invite_login(auth, admin)
        if case == "disabled":
            auth.change_user(admin.token, operator.user.id, None, False)
        elif case == "wrong":
            password = "wrong"
        else:
            with auth.factory.begin() as db:
                user = db.get(User, operator.user.id)
                user.role.code = "unexpected"
    with pytest.raises(AuthError, match="invalid_credentials") as error:
        auth.login(account, password, "client")
    assert error.value.status == 401


@pytest.mark.parametrize("offset,accepted", [(-0.000001, True), (0, False), (1, False)])
def test_idle_expiry_boundary(auth: AuthService, offset: float, accepted: bool) -> None:
    """Background reads do not renew idle time, even immediately before expiry."""
    admin = bootstrap_login(auth)
    auth.clock.advance(auth.settings.session_idle_seconds - 1)
    auth.current(admin.token)
    auth.clock.advance(1 + offset)
    if accepted:
        assert auth.current(admin.token).id == admin.user.id
    else:
        with pytest.raises(AuthError, match="authentication_required"):
            auth.current(admin.token)


def test_activity_renews_idle_but_never_absolute_expiry(auth: AuthService) -> None:
    """Foreground activity extends idle expiry; the absolute lifetime stays fixed."""
    admin = bootstrap_login(auth)
    for _ in range(47):
        auth.clock.advance(900)
        auth.current(admin.token, activity=True)
    auth.clock.advance(900)
    with pytest.raises(AuthError):
        auth.current(admin.token, activity=True)


def test_logout_replay_and_new_service_instance(auth: AuthService) -> None:
    """Sessions survive a service restart and server revocation prevents replay."""
    admin = bootstrap_login(auth)
    restarted = AuthService(auth.factory, auth.settings, auth.clock, auth.passwords)
    assert restarted.current(admin.token).id == admin.user.id
    restarted.logout(admin.token)
    auth.logout(admin.token)
    with pytest.raises(AuthError):
        auth.current(admin.token)


@pytest.mark.parametrize("role", ["admin", "operator", "reviewer"])
def test_permission_matrix_and_direct_bypass(auth: AuthService, role: str) -> None:
    """Role checks cover every operation, including direct service calls bypassing UI."""
    admin = bootstrap_login(auth)
    _, actor = invite_login(auth, admin, role, "another.user")
    expected = {
        "admin": set(Permission),
        "operator": {
            Permission.RUN_READ,
            Permission.RUN_CREATE,
            Permission.RUN_EDIT_OWN,
            Permission.MATERIAL_READ,
        },
        "reviewer": {
            Permission.RUN_READ,
            Permission.MATERIAL_READ,
            Permission.AUDIT_READ,
            Permission.EXPORT,
        },
    }[role]
    for permission in Permission:
        if permission in expected:
            auth.authorize(actor.token, permission)
        else:
            with pytest.raises(AuthError, match="permission_denied"):
                auth.authorize(actor.token, permission)
    if role != "admin":
        with pytest.raises(AuthError):
            auth.invite(actor.token, "bypass.user", "Bypass", "admin")
    assert actor.user.can_edit_run(actor.user.id) == (role != "reviewer")
    assert actor.user.can_edit_run(admin.user.id) == (role == "admin")
    with pytest.raises(AuthError):
        replace(actor.user, role="unknown").require(Permission.RUN_READ)


def test_role_change_and_disable_invalidate_old_sessions(auth: AuthService) -> None:
    """A downgraded or disabled user cannot continue with a previously valid cookie."""
    admin = bootstrap_login(auth)
    _, user = invite_login(auth, admin, "admin", "second.admin")
    auth.change_user(admin.token, user.user.id, "operator", None)
    with pytest.raises(AuthError):
        auth.current(user.token)
    replacement = auth.login(user.user.account, PASSWORD, "client")
    assert replacement.user.role == "operator"
    auth.change_user(admin.token, user.user.id, None, False)
    with pytest.raises(AuthError):
        auth.current(replacement.token)


@pytest.mark.parametrize("role,active", [("operator", None), (None, False)])
def test_final_admin_cannot_be_removed(
    auth: AuthService, role: str | None, active: bool | None
) -> None:
    """The last enabled Admin survives both disable and demotion attempts."""
    admin = bootstrap_login(auth)
    with pytest.raises(AuthError, match="final_admin_required"):
        auth.change_user(admin.token, admin.user.id, role, active)
    assert auth.current(admin.token).role == "admin"


def test_password_change_revokes_all_sessions_and_grants(auth: AuthService) -> None:
    """Changing a password invalidates old passwords, every session and outstanding links."""
    admin = bootstrap_login(auth)
    second = auth.login(admin.user.account, PASSWORD, "another-client")
    grant = auth.issue_grant(admin.token, admin.user.id, "recovery")
    with pytest.raises(AuthError):
        auth.change_password(admin.token, "wrong", REPLACEMENT)
    auth.change_password(admin.token, PASSWORD, REPLACEMENT)
    for token in (admin.token, second.token):
        with pytest.raises(AuthError):
            auth.current(token)
    with pytest.raises(AuthError):
        auth.consume_grant(grant.token, "recovery", PASSWORD, "client")
    with pytest.raises(AuthError):
        auth.login(admin.user.account, PASSWORD, "client")
    assert auth.login(admin.user.account, REPLACEMENT, "client").user.is_active


def test_recovery_is_single_use_and_does_not_leave_old_authority(auth: AuthService) -> None:
    """Admin recovery permits a new password once and revokes all earlier sessions."""
    admin = bootstrap_login(auth)
    _, user = invite_login(auth, admin)
    grant = auth.issue_grant(admin.token, user.user.id, "recovery")
    auth.consume_grant(grant.token, "recovery", REPLACEMENT, "client")
    with pytest.raises(AuthError):
        auth.consume_grant(grant.token, "recovery", PASSWORD, "client")
    with pytest.raises(AuthError):
        auth.current(user.token)
    assert auth.login(user.user.account, REPLACEMENT, "client").user.activated


def test_forced_password_change_has_only_password_and_logout_access(auth: AuthService) -> None:
    """Existing forced-change accounts cannot access ordinary protected operations."""
    admin = bootstrap_login(auth)
    with auth.factory.begin() as db:
        db.get(User, admin.user.id).must_change_password = True
    for operation in [lambda: auth.current(admin.token), lambda: auth.list_users(admin.token)]:
        with pytest.raises(AuthError, match="password_change_required"):
            operation()
    auth.change_password(admin.token, PASSWORD, REPLACEMENT)
    fresh = auth.login(admin.user.account, REPLACEMENT, "client")
    assert not fresh.user.must_change_password


def test_rate_limit_persists_and_recovers_at_deadline(auth: AuthService) -> None:
    """Service restarts cannot clear attempts; an expired window permits a retry."""
    admin = bootstrap_login(auth)
    for _ in range(auth.settings.login_account_limit):
        with pytest.raises(AuthError, match="invalid_credentials"):
            auth.login(admin.user.account, "wrong", "client")
    restarted = AuthService(auth.factory, auth.settings, auth.clock, auth.passwords)
    with pytest.raises(AuthError, match="too_many_attempts"):
        restarted.login(admin.user.account, PASSWORD, "client")
    auth.clock.advance(auth.settings.auth_window_seconds)
    assert restarted.login(admin.user.account, PASSWORD, "client").user.id == admin.user.id


def test_account_and_audit_roll_back_together(auth: AuthService) -> None:
    """Failure while writing the audit prevents the related account/grant commit."""
    admin = bootstrap_login(auth)
    engine = auth.factory.kw["bind"]

    def fail_audit(conn, cursor, statement, parameters, context, executemany) -> None:
        """Inject a persistence failure at the audit insert after account creation."""
        if "INSERT INTO audit_logs" in statement:
            raise RuntimeError("injected audit failure")

    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            auth.invite(admin.token, "rollback.user", "Rollback", "operator")
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    with auth.factory() as db:
        assert db.scalar(select(User).where(User.account == "rollback.user")) is None
        assert db.scalar(select(func.count(AccessGrant.id))) == 0
        assert db.scalar(select(AuditLog).where(AuditLog.action == "user_invited")) is None


def test_missing_auth_migration_fails_closed(auth: AuthService) -> None:
    """A missing coordination seed must not turn initialization into a public bootstrap."""
    with auth.factory.begin() as db:
        db.delete(db.get(AuthState, 1))
    with pytest.raises(AuthError, match="authentication_unavailable"):
        auth.bootstrap("admin", "Admin", PASSWORD)


def test_local_recovery_restores_only_an_existing_admin(auth: AuthService) -> None:
    """Trusted-console recovery restores an Admin and invalidates their old credentials."""
    admin = bootstrap_login(auth)
    _, operator = invite_login(auth, admin)
    with pytest.raises(AuthError, match="existing_admin_required"):
        auth.recover_admin(operator.user.account, REPLACEMENT)
    assert auth.recover_admin(admin.user.account, REPLACEMENT).is_active
    with pytest.raises(AuthError):
        auth.current(admin.token)


def test_session_tokens_are_new_for_each_login(auth: AuthService) -> None:
    """Concurrent valid sessions coexist and never reuse a previous token."""
    first = bootstrap_login(auth)
    second = auth.login(first.user.account, PASSWORD, "client")
    assert first.token != second.token
    assert auth.current(first.token).id == auth.current(second.token).id
    with auth.factory() as db:
        stored = list(db.scalars(select(LoginSession.token_digest)))
        assert first.token not in stored and second.token not in stored

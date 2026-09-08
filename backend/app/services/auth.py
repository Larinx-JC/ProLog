"""Authentication application service and transaction boundary for API/CLI callers."""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Passwords, Tokens, normalize_account
from app.core.time import Clock, SystemClock
from app.models import LoginSession, User
from app.services.auth_store import RateLimiter, audit, auth_transaction
from app.services.auth_types import AuthError, GrantIssued, Identity, Permission, SessionIssued
from app.services.invitations import InvitationService
from app.services.sessions import SessionService
from app.services.users import UserService


class AuthService:
    """Expose complete auth operations; callers never partially commit their work."""

    def __init__(
        self,
        factory: Callable[[], Session],
        settings: Settings,
        clock: Clock | None = None,
        passwords: Passwords | None = None,
    ) -> None:
        """Compose services with an injectable session factory, clock, and hasher."""
        self.factory, self.settings = factory, settings
        self.clock = clock or SystemClock()
        self.passwords = passwords or Passwords()
        self.tokens = Tokens(settings.secret_key)
        self.limiter = RateLimiter(settings, self.tokens)
        self.sessions = SessionService(settings, self.tokens)
        self.invitations = InvitationService(
            settings, self.tokens, self.passwords, self.sessions, self.limiter
        )
        self.users = UserService(self.passwords, self.sessions, self.invitations, self.limiter)

    def bootstrap(self, account: str, name: str, password: str) -> Identity:
        """Run first-Admin provisioning exclusively through the local CLI/service."""
        with auth_transaction(self.factory) as db:
            return self.users.bootstrap(db, account, name, password, self.clock.now())

    def recover_admin(self, account: str, password: str) -> Identity:
        """Restore an existing Admin without introducing a public recovery bypass."""
        with auth_transaction(self.factory) as db:
            return self.users.recover_admin(db, account, password, self.clock.now())

    def login(self, account: str, password: str, address: str) -> SessionIssued:
        """Authenticate generically, throttle attempts, and issue a fresh credential."""
        try:
            account = normalize_account(account)
        except ValueError:
            account = "!invalid-account"
        with auth_transaction(self.factory) as db:
            now = self.clock.now()
            self.limiter.consume(
                db,
                now,
                [
                    ("account", account, self.settings.login_account_limit),
                    ("login-address", address, self.settings.login_address_limit),
                ],
            )
            user = db.scalar(select(User).where(User.account == account))
            valid = self.passwords.verify(password, user.password_hash if user else None)
            if (
                not valid
                or user is None
                or not user.is_active
                or user.activated_at is None
                or user.role.code not in {"admin", "operator", "reviewer"}
            ):
                audit(db, now, "login_rejected")
                raise AuthError("invalid_credentials", 401, persist_failure=True)
            if self.passwords.needs_rehash(user.password_hash):
                user.password_hash = self.passwords.hash(password)
            self.limiter.clear_account(db, account)
            token = self.sessions.issue(db, user, now)
            audit(db, now, "login_succeeded", user, user)
            return SessionIssued(Identity.from_user(user), token)

    def current(self, token: str, activity: bool = False) -> Identity:
        """Read the current account; only an explicit foreground call renews idle time."""
        with auth_transaction(self.factory) as db:
            user, _ = self.sessions.require(db, token, self.clock.now(), activity=activity)
            return Identity.from_user(user)

    def authorize(self, token: str, permission: Permission) -> Identity:
        """Provide a reusable server-side permission check for later API sections."""
        identity = self.current(token)
        identity.require(permission)
        return identity

    def logout(self, token: str) -> None:
        """Revoke even an expired session, making repeated logout harmless."""
        with auth_transaction(self.factory) as db:
            row = db.scalar(
                select(LoginSession).where(LoginSession.token_digest == self.tokens.digest(token))
            )
            if row is not None and row.revoked_at is None:
                row.revoked_at = self.clock.now()
                user = db.get(User, row.user_id)
                audit(db, row.revoked_at, "logout", user, user)

    def _admin(self, db: Session, token: str, activity: bool = True) -> User:
        """Recheck current Admin authority within the mutation's transaction lock."""
        user, _ = self.sessions.require(db, token, self.clock.now(), activity=activity)
        Identity.from_user(user).require(Permission.USER_MANAGE)
        return user

    def _target(self, db: Session, user_id: int) -> User:
        """Resolve an Admin-selected account without exposing database details."""
        user = db.get(User, user_id)
        if user is None:
            raise AuthError("user_not_found", 404)
        return user

    def invite(
        self, token: str, account: str, name: str, role: str, position: str | None = None
    ) -> GrantIssued:
        """Provision an invited user and initial activation grant atomically."""
        with auth_transaction(self.factory) as db:
            actor = self._admin(db, token)
            return self.users.invite(db, actor, account, name, role, position, self.clock.now())

    def issue_grant(self, token: str, user_id: int, purpose: str) -> GrantIssued:
        """Let an Admin replace activation links or issue account recovery links."""
        with auth_transaction(self.factory) as db:
            actor = self._admin(db, token)
            return self.invitations.issue(
                db, self._target(db, user_id), actor, purpose, self.clock.now()
            )

    def consume_grant(self, token: str, purpose: str, password: str, address: str) -> Identity:
        """Activate/recover exactly once under the same lock as account revocation."""
        with auth_transaction(self.factory) as db:
            return self.invitations.consume(db, token, purpose, password, address, self.clock.now())

    def change_user(
        self, token: str, user_id: int, role: str | None, active: bool | None
    ) -> Identity:
        """Change account authority and invalidate all old sessions and grants."""
        if role is None and active is None:
            raise AuthError("no_changes_supplied")
        with auth_transaction(self.factory) as db:
            actor = self._admin(db, token)
            return self.users.change(
                db, actor, self._target(db, user_id), role, active, self.clock.now()
            )

    def list_users(self, token: str, offset: int = 0, limit: int = 50) -> list[Identity]:
        """Return bounded safe account records after checking current Admin authority."""
        if offset < 0 or not 1 <= limit <= 100:
            raise AuthError("invalid_pagination")
        with auth_transaction(self.factory) as db:
            self._admin(db, token, activity=False)
            rows = db.scalars(select(User).order_by(User.id).offset(offset).limit(limit))
            return [Identity.from_user(user) for user in rows]

    def change_password(self, token: str, current: str, replacement: str) -> None:
        """Require the current password, then revoke every previous credential."""
        with auth_transaction(self.factory) as db:
            now = self.clock.now()
            user, _ = self.sessions.require(db, token, now, allow_password_change=True)
            self.limiter.consume(
                db, now, [("password-change", str(user.id), self.settings.login_account_limit)]
            )
            if not self.passwords.verify(current, user.password_hash):
                audit(db, now, "password_change_rejected", user, user)
                raise AuthError("invalid_credentials", 401, persist_failure=True)
            user.password_hash = self.passwords.hash(replacement)
            user.must_change_password = False
            self.sessions.revoke_user(db, user.id, now)
            self.invitations.revoke_user(db, user.id, now)
            self.limiter.clear_account(db, user.account)
            audit(db, now, "password_changed", user, user)

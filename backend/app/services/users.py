"""Account provisioning and administration with final-Admin protection."""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Passwords, normalize_account
from app.models import AuthState, Role, User
from app.services.auth_store import RateLimiter, audit
from app.services.auth_types import ROLE_PERMISSIONS, AuthError, GrantIssued, Identity
from app.services.invitations import InvitationService
from app.services.sessions import SessionService


class UserService:
    """Account changes share a database lock with session and grant consumption."""

    def __init__(
        self,
        passwords: Passwords,
        sessions: SessionService,
        invitations: InvitationService,
        limiter: RateLimiter,
    ) -> None:
        """Reuse hashing and revocation services for every account change."""
        self.passwords, self.sessions = passwords, sessions
        self.invitations, self.limiter = invitations, limiter

    def role(self, db: Session, code: str) -> Role:
        """Accept only the agreed seeded roles, failing closed on unknown codes."""
        role = db.scalar(select(Role).where(Role.code == code))
        if code not in ROLE_PERMISSIONS or role is None:
            raise AuthError("invalid_role")
        return role

    def bootstrap(
        self, db: Session, account: str, name: str, password: str, now: datetime
    ) -> Identity:
        """Create the first Admin exactly once under the seeded coordination lock."""
        state = db.get(AuthState, 1)
        assert state is not None
        existing = db.scalar(select(User.id).join(Role).where(Role.code == "admin").limit(1))
        if state.bootstrap_completed or existing is not None:
            raise AuthError("bootstrap_already_completed", 409)
        user = self._new_user(db, account, name, "admin", None)
        user.password_hash = self.passwords.hash(password)
        user.is_active = True
        user.must_change_password = False
        user.activated_at = now
        state.bootstrap_completed = True
        db.flush()
        audit(db, now, "admin_bootstrapped", target=user, reason="Local interactive setup")
        return Identity.from_user(user)

    def _new_user(
        self, db: Session, account: str, name: str, role: str, position: str | None
    ) -> User:
        """Build an inactive account after validating its identifier and role."""
        account = normalize_account(account)
        name = name.strip()
        if not name or len(name) > 100 or (position is not None and len(position) > 100):
            raise AuthError("invalid_user_details")
        if db.scalar(select(User.id).where(User.account == account)) is not None:
            raise AuthError("account_exists", 409)
        user = User(
            account=account,
            name=name,
            position=position,
            role=self.role(db, role),
            password_hash="!pending-activation",
            is_active=False,
            must_change_password=True,
            activated_at=None,
        )
        db.add(user)
        db.flush()
        return user

    def invite(
        self,
        db: Session,
        actor: User,
        account: str,
        name: str,
        role: str,
        position: str | None,
        now: datetime,
    ) -> GrantIssued:
        """Create an inactive account and its first activation grant atomically."""
        user = self._new_user(db, account, name, role, position)
        audit(db, now, "user_invited", actor, user, after=role)
        return self.invitations.issue(db, user, actor, "activation", now)

    def change(
        self,
        db: Session,
        actor: User,
        user: User,
        role_code: str | None,
        active: bool | None,
        now: datetime,
    ) -> Identity:
        """Prevent removal of the final active Admin and invalidate stale authority."""
        before = json.dumps({"role": user.role.code, "is_active": user.is_active})
        role = self.role(db, role_code) if role_code is not None else user.role
        enabled = active if active is not None else user.is_active
        if enabled and user.activated_at is None:
            raise AuthError("activation_required", 409)
        if user.is_active and user.role.code == "admin" and (not enabled or role.code != "admin"):
            count = db.scalar(
                select(func.count(User.id))
                .join(Role)
                .where(
                    Role.code == "admin", User.is_active.is_(True), User.activated_at.is_not(None)
                )
            )
            if count is None or count <= 1:
                raise AuthError("final_admin_required", 409)
        user.role = role
        user.is_active = enabled
        self.sessions.revoke_user(db, user.id, now)
        self.invitations.revoke_user(db, user.id, now)
        audit(
            db,
            now,
            "user_authority_changed",
            actor,
            user,
            before=before,
            after=json.dumps({"role": role.code, "is_active": enabled}),
        )
        db.flush()
        return Identity.from_user(user)

    def recover_admin(self, db: Session, account: str, password: str, now: datetime) -> Identity:
        """Restore an existing Admin from the trusted local console, with an audit."""
        user = db.scalar(select(User).where(User.account == normalize_account(account)))
        if user is None or user.role.code != "admin":
            raise AuthError("existing_admin_required", 404)
        user.password_hash = self.passwords.hash(password)
        user.activated_at = user.activated_at or now
        user.is_active = True
        user.must_change_password = False
        self.sessions.revoke_user(db, user.id, now)
        self.invitations.revoke_user(db, user.id, now)
        self.limiter.clear_account(db, user.account)
        audit(db, now, "admin_recovered_locally", target=user, reason="Local interactive recovery")
        db.flush()
        return Identity.from_user(user)

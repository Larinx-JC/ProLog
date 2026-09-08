"""Creation, current-state validation, and revocation of persistent sessions."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Tokens
from app.models import LoginSession, User
from app.services.auth_types import ROLE_PERMISSIONS, AuthError


class SessionService:
    """Validate user state on every request; background reads never extend expiry."""

    def __init__(self, settings: Settings, tokens: Tokens) -> None:
        """Accept the same validated settings and token primitives as other services."""
        self.settings = settings
        self.tokens = tokens

    def issue(self, db: Session, user: User, now: datetime) -> str:
        """Create a new opaque credential without accepting a caller-chosen token."""
        token = self.tokens.issue()
        db.add(
            LoginSession(
                token_digest=self.tokens.digest(token),
                user_id=user.id,
                created_at=now,
                last_activity_at=now,
                expires_at=now + timedelta(seconds=self.settings.session_max_seconds),
            )
        )
        return token

    def require(
        self,
        db: Session,
        token: str,
        now: datetime,
        activity: bool = False,
        allow_password_change: bool = False,
    ) -> tuple[User, LoginSession]:
        """Reject expired/revoked credentials and read current privileges from MySQL."""
        row = db.scalar(
            select(LoginSession).where(LoginSession.token_digest == self.tokens.digest(token))
        )
        user = db.get(User, row.user_id) if row else None
        if (
            row is None
            or user is None
            or row.revoked_at is not None
            or not user.is_active
            or user.activated_at is None
            or user.role.code not in ROLE_PERMISSIONS
            or now < row.created_at
            or now >= row.expires_at
            or now >= row.last_activity_at + timedelta(seconds=self.settings.session_idle_seconds)
        ):
            raise AuthError("authentication_required", 401)
        if user.must_change_password and not allow_password_change:
            raise AuthError("password_change_required", 403)
        if activity:
            row.last_activity_at = max(now, row.last_activity_at)
        return user, row

    def revoke_user(self, db: Session, user_id: int, now: datetime) -> None:
        """Invalidate every session after a password, role, or account-status change."""
        db.execute(
            update(LoginSession)
            .where(LoginSession.user_id == user_id, LoginSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

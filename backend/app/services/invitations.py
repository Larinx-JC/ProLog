"""Admin-issued single-use activation and recovery grants."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Passwords, Tokens
from app.models import AccessGrant, User
from app.services.auth_store import RateLimiter, audit
from app.services.auth_types import AuthError, GrantIssued, Identity
from app.services.sessions import SessionService


class InvitationService:
    """Consume grants and change credentials within the shared auth transaction."""

    def __init__(
        self,
        settings: Settings,
        tokens: Tokens,
        passwords: Passwords,
        sessions: SessionService,
        limiter: RateLimiter,
    ) -> None:
        """Compose shared security primitives rather than duplicate credential logic."""
        self.settings, self.tokens, self.passwords = settings, tokens, passwords
        self.sessions, self.limiter = sessions, limiter

    def revoke_user(self, db: Session, user_id: int, now: datetime) -> None:
        """Invalidate all outstanding links when account authority changes."""
        db.execute(
            update(AccessGrant)
            .where(
                AccessGrant.user_id == user_id,
                AccessGrant.revoked_at.is_(None),
                AccessGrant.consumed_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def issue(
        self, db: Session, user: User, actor: User, purpose: str, now: datetime
    ) -> GrantIssued:
        """Reissuing replaces prior links; only the returned URL contains the secret."""
        if purpose not in {"activation", "recovery"}:
            raise AuthError("invalid_grant_purpose")
        if purpose == "activation" and user.activated_at is not None:
            raise AuthError("account_already_activated", 409)
        if purpose == "recovery" and (user.activated_at is None or not user.is_active):
            raise AuthError("account_not_eligible", 409)
        self.revoke_user(db, user.id, now)
        token = self.tokens.issue()
        seconds = (
            self.settings.activation_seconds
            if purpose == "activation"
            else self.settings.recovery_seconds
        )
        db.add(
            AccessGrant(
                token_digest=self.tokens.digest(token),
                user_id=user.id,
                issued_by_id=actor.id,
                purpose=purpose,
                created_at=now,
                expires_at=now + timedelta(seconds=seconds),
            )
        )
        audit(db, now, f"{purpose}_issued", actor, user)
        path = "activate" if purpose == "activation" else "recover"
        return GrantIssued(
            Identity.from_user(user),
            purpose,
            f"{self.settings.public_url}/{path}#token={token}",
            token,
        )

    def consume(
        self, db: Session, token: str, purpose: str, password: str, address: str, now: datetime
    ) -> Identity:
        """Accept one valid link exactly once; commit failed-attempt counters safely."""
        self.limiter.consume(
            db, now, [("grant-address", address, self.settings.grant_address_limit)]
        )
        grant = db.scalar(
            select(AccessGrant).where(AccessGrant.token_digest == self.tokens.digest(token))
        )
        user = db.get(User, grant.user_id) if grant else None
        if (
            grant is None
            or user is None
            or grant.purpose != purpose
            or grant.revoked_at is not None
            or grant.consumed_at is not None
            or now >= grant.expires_at
            or now < grant.created_at
            or (purpose == "activation" and user.activated_at is not None)
            or (purpose == "recovery" and (not user.is_active or user.activated_at is None))
        ):
            audit(db, now, "grant_rejected")
            raise AuthError("invalid_or_expired_link", 400, persist_failure=True)
        user.password_hash = self.passwords.hash(password)
        user.activated_at = user.activated_at or now
        user.is_active = True
        user.must_change_password = False
        grant.consumed_at = now
        db.flush()
        self.sessions.revoke_user(db, user.id, now)
        self.revoke_user(db, user.id, now)
        self.limiter.clear_account(db, user.account)
        audit(db, now, f"{purpose}_completed", user, user)
        db.flush()
        return Identity.from_user(user)

"""Persistent authentication state; credentials are stored only as digests."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

AUTH_TIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")


class AuthState(Base):
    """Seeded singleton coordinating short authentication transactions across workers."""

    __tablename__ = "auth_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_auth_state_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    bootstrap_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )


class LoginSession(Base):
    """Revocable server-side session with independent idle and absolute deadlines."""

    __tablename__ = "login_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_login_sessions_expiry"),
        CheckConstraint("last_activity_at >= created_at", name="ck_login_sessions_activity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(AUTH_TIME)
    last_activity_at: Mapped[datetime] = mapped_column(AUTH_TIME)
    expires_at: Mapped[datetime] = mapped_column(AUTH_TIME, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AUTH_TIME, default=None)


class AccessGrant(Base):
    """A single-use activation or recovery capability issued by a permitted Admin."""

    __tablename__ = "access_grants"
    __table_args__ = (
        CheckConstraint("purpose IN ('activation', 'recovery')", name="ck_access_grants_purpose"),
        CheckConstraint("expires_at > created_at", name="ck_access_grants_expiry"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    purpose: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(AUTH_TIME)
    expires_at: Mapped[datetime] = mapped_column(AUTH_TIME, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(AUTH_TIME, default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(AUTH_TIME, default=None)


class AuthThrottle(Base):
    """Expiring attempt counters keyed by HMACs of account/client-address scopes."""

    __tablename__ = "auth_throttles"
    __table_args__ = (CheckConstraint("attempts >= 0", name="ck_auth_throttles_attempts"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(AUTH_TIME, index=True)

"""User: an account, created by an Admin (no self-registration)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.auth import AUTH_TIME
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.role import Role


class User(TimestampMixin, Base):
    """A person who can sign in: an Admin, Operator, or Reviewer."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    account: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(100), default=None)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    activated_at: Mapped[datetime | None] = mapped_column(AUTH_TIME, default=None)

    role: Mapped["Role"] = relationship(back_populates="users")

    def __repr__(self) -> str:
        """Identify the account without exposing its password hash."""
        return f"User(account={self.account!r})"

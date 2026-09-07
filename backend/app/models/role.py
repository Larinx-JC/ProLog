"""Role: the small, fixed set of privilege levels a User can hold."""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User

# Seeded by the Section 2 migration; code is what services/permission
# checks compare against, display_name is what the (Chinese-language) UI
# shows a human.
ADMIN = "admin"
OPERATOR = "operator"
REVIEWER = "reviewer"


class Role(Base):
    """A privilege level: Admin, Operator, or Reviewer.

    A normalized table rather than a bare enum column on User so a future
    role (or per-role metadata) is a data change, not a migration.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255), default=None)

    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"Role(code={self.code!r})"

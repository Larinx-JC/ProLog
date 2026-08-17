"""AuditLog: a simple before/after/reason trail across entity types."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """One recorded change: who did what to what, and why.

    Deliberately free-text before/after values (matching the original
    design) rather than a structured per-field diff system -- nothing in
    the specified workflow needs field-level diffing, and building that
    now would be speculative.

    target_id has no FK constraint since it references different tables
    depending on target_type (a "run", a "material", a "user", ...).
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int | None] = mapped_column(default=None)
    target_label: Mapped[str] = mapped_column(String(255))

    before_value: Mapped[str | None] = mapped_column(Text, default=None)
    after_value: Mapped[str | None] = mapped_column(Text, default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    actor: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return f"AuditLog(target_type={self.target_type!r}, target_label={self.target_label!r})"

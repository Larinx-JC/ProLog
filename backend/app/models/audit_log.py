"""AuditLog: a simple action/before/after/reason trail across entity types."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """One recorded change: who did what to what, and why.

    `action` is a short machine-readable code naming the event, e.g.
    "run_created", "run_closed", "run_reviewed", "measurement_edited",
    "material_deactivated", "user_disabled", "export_generated",
    "import_performed" -- not a fixed enum, since the set of actions
    grows as each later section adds its own (Section 4's RunService,
    Section 7's export, Section 8's ingestion, ...).

    before_value/after_value are deliberately free text (matching the
    original design) rather than a structured per-field diff system --
    nothing in the specified workflow needs field-level diffing, and
    building that now would be speculative.

    target_id has no FK constraint since it references different tables
    depending on target_type (a "run", a "material", a "user", ...).

    occurred_at is a naive datetime representing UTC by convention (see
    app.core.time / docs/data-model.md), generated in application code
    rather than by the database server.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    action: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int | None] = mapped_column(default=None)
    target_label: Mapped[str] = mapped_column(String(255))

    before_value: Mapped[str | None] = mapped_column(Text, default=None)
    after_value: Mapped[str | None] = mapped_column(Text, default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    actor: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        """Identify the audit action and target without dumping change details."""
        return f"AuditLog(action={self.action!r}, target_label={self.target_label!r})"

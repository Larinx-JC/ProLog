"""Material: a detected material's standard value and abnormality rules."""

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import AbnormalityRulesMixin, TimestampMixin, abnormality_rule_constraints


class Material(TimestampMixin, AbnormalityRulesMixin, Base):
    """A material's current standard and the rules used to flag a
    measurement or run as abnormal (fields from AbnormalityRulesMixin).

    These are the *current, editable* rules -- used as the default when
    starting a new Run. Run has its own copy of the same mixin fields,
    snapshotted at creation time, so changing a Material's rules here
    later never changes how an existing run's measurements are judged.
    """

    __tablename__ = "materials"
    __table_args__ = abnormality_rule_constraints("materials")

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    material_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # Soft delete: a Material referenced by historical Runs can't be hard-
    # deleted without orphaning their foreign key, so "deleting" a material
    # in the UI just deactivates it (excluded from the "start new run"
    # material picker, kept for existing runs' history).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))

    def __repr__(self) -> str:
        """Identify the material in debugger output."""
        return f"Material(material_no={self.material_no!r})"

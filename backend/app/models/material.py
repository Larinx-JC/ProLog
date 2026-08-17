"""Material: a detected material's standard value and abnormality rules."""

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin

# All numeric columns use DECIMAL(10, 2) uniformly (never float) per the
# project's fixed-point numeric policy -- see CONTRIBUTING.md.
_DECIMAL = Numeric(10, 2)


class Material(TimestampMixin, Base):
    """A material's current standard and the rules used to flag a
    measurement or run as abnormal.

    standard_value here is the *current* value used as the default when
    starting a new Run. A Run snapshots this value into its own
    standard_value column at creation time, so changing a Material's
    standard later never changes how an already-started (or completed)
    run's measurements are judged.
    """

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    standard_value: Mapped[Decimal] = mapped_column(_DECIMAL)
    upper_limit: Mapped[Decimal] = mapped_column(_DECIMAL)
    lower_limit: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_min: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_max: Mapped[Decimal] = mapped_column(_DECIMAL)
    deviation_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deviation_pct_threshold: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limits_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Soft delete: a Material referenced by historical Runs can't be hard-
    # deleted without orphaning their foreign key, so "deleting" a material
    # in the UI just deactivates it (excluded from the "start new run"
    # material picker, kept for existing runs' history).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"Material(material_no={self.material_no!r})"

"""Run: one production/detection run, from start through review."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ReviewResolution, RunStatus, sa_enum
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.material import Material
    from app.models.measurement import Measurement
    from app.models.user import User

_DECIMAL = Numeric(10, 2)


class Run(TimestampMixin, Base):
    """One run of the detection line: created against a Material, records
    Measurements while active, and ends in REVIEWED after passing through
    review. See app.models.enums.RunStatus for the full state machine.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    # Snapshotted from Material.standard_value at creation time -- always
    # read this column (never the live Material) when judging whether a
    # measurement on THIS run is abnormal, so a later change to the
    # material's standard can't retroactively change this run's history.
    standard_value: Mapped[Decimal] = mapped_column(_DECIMAL)
    raw_material_batch: Mapped[str] = mapped_column(String(100))
    interval_seconds: Mapped[int] = mapped_column()

    status: Mapped[RunStatus] = mapped_column(sa_enum(RunStatus), default=RunStatus.ACTIVE)
    # Which status this run was in immediately before entering
    # PENDING_REVIEW (ACTIVE or ABNORMAL) -- None until it does.
    pending_from: Mapped[RunStatus | None] = mapped_column(sa_enum(RunStatus), default=None)

    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime | None] = mapped_column(default=None)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    review_resolution: Mapped[ReviewResolution | None] = mapped_column(
        sa_enum(ReviewResolution), default=None
    )
    review_reason: Mapped[str | None] = mapped_column(Text, default=None)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)

    material: Mapped["Material"] = relationship()
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="run", order_by="Measurement.measurement_time"
    )

    def __repr__(self) -> str:
        return f"Run(run_code={self.run_code!r}, status={self.status!r})"

"""Run: one production/detection run, from start through review."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ReviewResolution, RunStatus, sa_enum
from app.models.mixins import AbnormalityRulesMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.material import Material
    from app.models.measurement import Measurement
    from app.models.user import User


class Run(TimestampMixin, AbnormalityRulesMixin, Base):
    """One run of the detection line: created against a Material, records
    Measurements while active, and ends in REVIEWED after passing through
    review. See app.models.enums.RunStatus for the full state machine.

    The AbnormalityRulesMixin fields (standard_value, upper_limit, ...)
    are a full snapshot of the Material's rules taken at creation time --
    always read them from THIS row (never the live Material) when judging
    whether a measurement on this run is abnormal. Otherwise editing a
    Material's rules mid-run would judge earlier and later measurements
    in the same run by different rules, and a run's history could no
    longer be reconstructed once the material moves on.

    All datetime columns here (start_time, end_time, reviewed_at, plus
    created_at/updated_at from TimestampMixin) are naive datetimes that
    represent UTC by convention -- see app.core.time and
    docs/data-model.md's time policy.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
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

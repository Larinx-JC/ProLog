"""Measurement: one detection row within a Run."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import EntryMethod, MeasurementStatus, sa_enum

if TYPE_CHECKING:
    from app.models.run import Run
    from app.models.user import User

_DECIMAL = Numeric(10, 2)


class Measurement(Base):
    """One row of detection data recorded within a Run.

    average_value/max_deviation/deviation_percent are computed (from
    point_1..point_4) when the row is marked complete, not entered
    directly -- see the Section 4 AbnormalityDetector.

    measurement_time/recorded_at are naive datetimes representing UTC by
    convention -- see app.core.time / docs/data-model.md.
    """

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))

    measurement_time: Mapped[datetime] = mapped_column()
    meter_count: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    speed: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    point_1: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    point_2: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    point_3: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    point_4: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    thickness: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    average_value: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    max_deviation: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)
    deviation_percent: Mapped[Decimal | None] = mapped_column(_DECIMAL, default=None)

    status: Mapped[MeasurementStatus] = mapped_column(
        sa_enum(MeasurementStatus), default=MeasurementStatus.MISSING
    )
    # Reserves the ingestion-portal (outline Section 8) distinction now,
    # at the cost of a single column, rather than a full speculative field
    # set for a section that isn't scoped yet.
    entry_method: Mapped[EntryMethod] = mapped_column(
        sa_enum(EntryMethod), default=EntryMethod.MANUAL
    )

    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    recorded_at: Mapped[datetime | None] = mapped_column(default=None)

    run: Mapped["Run"] = relationship(back_populates="measurements")
    recorded_by: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return f"Measurement(run_id={self.run_id!r}, status={self.status!r})"

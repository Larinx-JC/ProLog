"""Measurement: one detection row within a Run."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import EntryMethod, MeasurementStatus, sa_enum
from app.models.mixins import PRECISE_TIME, PRODUCTION_DECIMAL

if TYPE_CHECKING:
    from app.models.run import Run
    from app.models.user import User

_DECIMAL = PRODUCTION_DECIMAL


class Measurement(Base):
    """One row of detection data recorded within a Run.

    average_value/max_deviation/deviation_percent are computed (from
    point_1..point_4) when the row is marked complete, not entered
    directly -- see the Section 4 AbnormalityDetector.

    measurement_time/recorded_at are naive datetimes representing UTC by
    convention -- see app.core.time / docs/data-model.md.
    """

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("run_id", "slot_index", name="uq_measurement_run_slot"),
        CheckConstraint("slot_index IS NULL OR slot_index >= 0", name="ck_measurement_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    slot_index: Mapped[int | None] = mapped_column()
    alarm_codes: Mapped[list | None] = mapped_column(JSON)

    measurement_time: Mapped[datetime] = mapped_column(PRECISE_TIME)
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
    target_deviation: Mapped[Decimal | None] = mapped_column(_DECIMAL)
    target_deviation_percent: Mapped[Decimal | None] = mapped_column(_DECIMAL)

    status: Mapped[MeasurementStatus] = mapped_column(
        sa_enum(MeasurementStatus), default=MeasurementStatus.MISSING, server_default="missing"
    )
    # Reserves the ingestion-portal (outline Section 8) distinction now,
    # at the cost of a single column, rather than a full speculative field
    # set for a section that isn't scoped yet.
    entry_method: Mapped[EntryMethod] = mapped_column(
        sa_enum(EntryMethod), default=EntryMethod.MANUAL, server_default="manual"
    )

    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    recorded_at: Mapped[datetime | None] = mapped_column(PRECISE_TIME, default=None)

    run: Mapped["Run"] = relationship(back_populates="measurements")
    recorded_by: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        """Show the owning run and measurement completion state."""
        return f"Measurement(run_id={self.run_id!r}, status={self.status!r})"

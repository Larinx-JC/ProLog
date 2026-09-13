"""Run: one production/detection run, from start through review."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ReviewResolution, RunStatus, sa_enum
from app.models.mixins import (
    PRECISE_TIME,
    AbnormalityRulesMixin,
    TimestampMixin,
    abnormality_rule_constraints,
)

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

    __table_args__ enforces the structural invariants that are always
    true regardless of workflow (valid rule ranges, end_time can't
    precede start_time, pending_from can only be active/abnormal).
    Status-conditional invariants -- e.g. status=reviewed implies
    reviewed_by/review_resolution/reviewed_at are set, status=active
    implies they aren't, pending_from is only set once a run has entered
    PENDING_REVIEW -- are deliberately NOT database constraints. They're
    workflow transitions, not static row shape, and belong to Section
    4's RunService/ReviewService (the sole writers of these columns),
    tested comprehensively there rather than duplicated as increasingly
    complex CHECK expressions here that would need a migration every
    time the state machine evolves.
    """

    __tablename__ = "runs"
    __table_args__ = (
        *abnormality_rule_constraints("runs"),
        CheckConstraint("interval_seconds > 0", name="ck_runs_interval_positive"),
        CheckConstraint(
            "pending_from IS NULL OR pending_from IN ('active', 'abnormal')",
            name="ck_runs_pending_from_valid",
        ),
        CheckConstraint(
            "end_time IS NULL OR end_time >= start_time", name="ck_runs_end_after_start"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    accuracy_version_id: Mapped[int | None] = mapped_column(ForeignKey("accuracy_versions.id"))
    missing_count_at_close: Mapped[int | None] = mapped_column()
    closure_exception_reason: Mapped[str | None] = mapped_column(Text)
    run_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    raw_material_batch: Mapped[str] = mapped_column(String(100))
    interval_seconds: Mapped[int] = mapped_column()

    status: Mapped[RunStatus] = mapped_column(
        sa_enum(RunStatus), default=RunStatus.ACTIVE, server_default="active"
    )
    # Which status this run was in immediately before entering
    # PENDING_REVIEW (ACTIVE or ABNORMAL) -- None until it does.
    pending_from: Mapped[RunStatus | None] = mapped_column(sa_enum(RunStatus), default=None)

    start_time: Mapped[datetime] = mapped_column(PRECISE_TIME)
    end_time: Mapped[datetime | None] = mapped_column(PRECISE_TIME, default=None)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    review_resolution: Mapped[ReviewResolution | None] = mapped_column(
        sa_enum(ReviewResolution), default=None
    )
    review_reason: Mapped[str | None] = mapped_column(Text, default=None)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(PRECISE_TIME, default=None)

    material: Mapped["Material"] = relationship()
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="run", order_by="Measurement.measurement_time"
    )

    def __repr__(self) -> str:
        """Identify the production run and its current lifecycle state."""
        return f"Run(run_code={self.run_code!r}, status={self.status!r})"

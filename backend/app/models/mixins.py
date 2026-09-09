"""Reusable column mixins shared across ORM models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow

# Extra result capacity accommodates percentages against very small targets.
PRODUCTION_DECIMAL = Numeric(24, 6)
PRECISE_TIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")
_DECIMAL = PRODUCTION_DECIMAL


class TimestampMixin:
    """created_at/updated_at columns for entities with a real lifecycle.

    Not applied to Measurement (its lifecycle is already captured by the
    domain-specific measurement_time/recorded_at columns) or AuditLog
    (a single immutable occurred_at is more precise than created/updated).

    Uses app.core.time.utcnow (Python-generated) rather than
    server_default=func.now() (MySQL-generated) so the UTC guarantee
    doesn't depend on the database server's timezone configuration.
    """

    created_at: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow, onupdate=utcnow)


class AbnormalityRulesMixin:
    """The detection thresholds used to judge whether a measurement/run
    is abnormal: a standard value, upper/lower/thickness bounds, and
    which checks are enabled.

    Shared by Material (the live, editable rules) and Run (an immutable
    snapshot of those rules taken at creation time) so that editing a
    Material's rules later can never retroactively change how an
    existing run's measurements are judged -- including measurements
    added to a still-active run after the edit.
    """

    standard_value: Mapped[Decimal] = mapped_column(_DECIMAL)
    upper_limit: Mapped[Decimal] = mapped_column(_DECIMAL)
    lower_limit: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_min: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_max: Mapped[Decimal] = mapped_column(_DECIMAL)
    deviation_check_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    deviation_pct_threshold: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_check_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    limits_check_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )


def abnormality_rule_constraints(table_name: str) -> tuple[CheckConstraint, ...]:
    """CHECK constraints enforcing internally-consistent abnormality
    rules, shared by materials (live) and runs (snapshotted) since both
    use AbnormalityRulesMixin.

    Called explicitly from each model's __table_args__ (rather than via
    a mixin-level @declared_attr __table_args__) to keep combining them
    with a model's own additional constraints straightforward. MySQL
    requires CHECK constraint names to be unique per-database, not just
    per-table, hence the table_name prefix.
    """
    return (
        CheckConstraint("lower_limit <= upper_limit", name=f"ck_{table_name}_limits_order"),
        CheckConstraint("thickness_min <= thickness_max", name=f"ck_{table_name}_thickness_order"),
        CheckConstraint("deviation_pct_threshold >= 0", name=f"ck_{table_name}_deviation_nonneg"),
    )

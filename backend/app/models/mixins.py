"""Reusable column mixins shared across ORM models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow

_DECIMAL = Numeric(10, 2)


class TimestampMixin:
    """created_at/updated_at columns for entities with a real lifecycle.

    Not applied to Measurement (its lifecycle is already captured by the
    domain-specific measurement_time/recorded_at columns) or AuditLog
    (a single immutable occurred_at is more precise than created/updated).

    Uses app.core.time.utcnow (Python-generated) rather than
    server_default=func.now() (MySQL-generated) so the UTC guarantee
    doesn't depend on the database server's timezone configuration.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


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
    deviation_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deviation_pct_threshold: Mapped[Decimal] = mapped_column(_DECIMAL)
    thickness_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limits_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

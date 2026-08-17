"""Reusable column mixins shared across ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """created_at/updated_at columns for entities with a real lifecycle.

    Not applied to Measurement (its lifecycle is already captured by the
    domain-specific measurement_time/recorded_at columns) or AuditLog
    (a single immutable occurred_at is more precise than created/updated).
    """

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

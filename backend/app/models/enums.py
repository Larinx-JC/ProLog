"""Shared status/category vocabularies used across ORM models.

Centralizing these as Python enums (rather than bare strings scattered
across models/services) means SQLAlchemy enforces valid values at the
column level and every layer above (services, API, frontend) has one
canonical source for what a status can be.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import TypeEngine


class RunStatus(StrEnum):
    """A run's position in its lifecycle.

    ACTIVE ──(measurement flagged abnormal)──> ABNORMAL
    ACTIVE/ABNORMAL ──(close)──> PENDING_REVIEW
    PENDING_REVIEW ──(review)──> REVIEWED  [terminal]

    There is deliberately no "closed without review" status — every run
    reaches its terminal state through review.
    """

    ACTIVE = "active"
    ABNORMAL = "abnormal"
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"


class MeasurementStatus(StrEnum):
    """A single measurement row's completion state."""

    MISSING = "missing"
    COMPLETED = "completed"
    ABNORMAL = "abnormal"


class ReviewResolution(StrEnum):
    """The outcome recorded when a run is reviewed.

    APPROVED applies to a run that entered review directly from ACTIVE.
    CONFIRMED_ABNORMAL / FALSE_ALARM only apply to a run that entered
    review from ABNORMAL (pending_from=ABNORMAL) — the reviewer decides
    which one.
    """

    APPROVED = "approved"
    CONFIRMED_ABNORMAL = "confirmed_abnormal"
    FALSE_ALARM = "false_alarm"


class EntryMethod(StrEnum):
    """How a measurement's values were entered.

    MANUAL is the only path today. AUTOMATED is reserved for the future
    ingestion portal (outline Section 8) so that work doesn't require a
    schema migration to distinguish automated from manual entries.
    """

    MANUAL = "manual"
    AUTOMATED = "automated"


def sa_enum(enum_cls: type[StrEnum]) -> TypeEngine:
    """Build a SQLAlchemy Enum column type storing each member's string
    .value (e.g. "pending_review") rather than its Python attribute name.

    Centralized so every model's enum column is configured identically
    instead of repeating `values_callable=...` per column. validate_strings
    makes an invalid raw string raise at flush time on every backend --
    without it, SQLAlchemy's Enum only relies on the database to reject
    bad values (MySQL's native ENUM does; SQLite, used by the fast
    model-level tests, does not by default).
    """
    return SAEnum(
        enum_cls, values_callable=lambda x: [e.value for e in x], validate_strings=True
    )

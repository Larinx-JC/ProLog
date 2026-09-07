"""Unit tests for app.core.time.utcnow -- the project's UTC time policy.

The rest of the suite only exercises this indirectly (it runs every time
a model with TimestampMixin/AuditLog is created), which gives statement
coverage without ever asserting the two things that actually matter:
the result is naive (no tzinfo), and it's genuinely "now" in UTC.
"""

from datetime import UTC, datetime

from app.core.time import utcnow


def test_utcnow_is_timezone_naive() -> None:
    """The stored convention only works if every value is naive -- a
    stray tz-aware datetime slipping into a DATETIME column would be a
    silent policy violation, not an error."""
    assert utcnow().tzinfo is None


def test_utcnow_represents_the_current_utc_instant() -> None:
    """The naive value must actually be "now" in UTC, not e.g. local
    time with tzinfo stripped (which would be silently wrong in any
    timezone other than UTC)."""
    before = datetime.now(UTC).replace(tzinfo=None)
    result = utcnow()
    after = datetime.now(UTC).replace(tzinfo=None)

    assert before <= result <= after

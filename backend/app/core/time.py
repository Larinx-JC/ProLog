"""UTC time policy.

Every timestamp stored in the database is a naive datetime (no tzinfo)
that represents UTC by convention -- never local/server time. Converting
to the factory's configured timezone happens only at the display layer
(frontend / export formatting), never in the database or domain model.

Timestamps are generated in application code via utcnow() below, not via
the database server's NOW() (SQLAlchemy's server_default=func.now()) --
that would make correctness depend on the MySQL server's session/global
time_zone being configured to UTC, an operational detail this app
shouldn't have to trust. See docs/data-model.md.
"""

from datetime import UTC, datetime
from typing import Protocol


def utcnow() -> datetime:
    """The current instant, as a naive datetime representing UTC.

    The one function every DB timestamp default should call, so the UTC
    convention can't accidentally drift by someone using datetime.now()
    (local/server time) somewhere instead.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Clock(Protocol):
    """Injectable source of UTC-naive instants for service expiry decisions."""

    def now(self) -> datetime:
        """Return the current UTC instant without timezone metadata."""
        ...


class SystemClock:
    """Production clock following the shared UTC storage convention."""

    def now(self) -> datetime:
        """Read the shared UTC helper rather than workstation-local time."""
        return utcnow()

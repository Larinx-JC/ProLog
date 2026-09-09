"""Factory time normalization and deterministic scheduled-sample identities."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.numeric import DomainError

FACTORY_TIMEZONE = ZoneInfo("Asia/Shanghai")


class ProductionTime:
    """Normalize explicit factory input; all service/database instants remain UTC-naive."""

    @staticmethod
    def parse(value: str) -> datetime:
        """Accept ISO timestamps; naive input means Shanghai and ambiguous times are rejected."""
        if not isinstance(value, str) or not 19 <= len(value) <= 40:
            raise DomainError("invalid_measurement_time")
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                first = parsed.replace(tzinfo=FACTORY_TIMEZONE, fold=0)
                second = parsed.replace(tzinfo=FACTORY_TIMEZONE, fold=1)
                utc = first.astimezone(UTC)
                if (
                    first.utcoffset() != second.utcoffset()
                    or utc.astimezone(FACTORY_TIMEZONE).replace(tzinfo=None) != parsed
                ):
                    raise DomainError("ambiguous_factory_time")
                parsed = utc
            return parsed.astimezone(UTC).replace(tzinfo=None)
        except (ValueError, OverflowError) as error:
            raise DomainError("invalid_measurement_time") from error

    @staticmethod
    def validate(value: datetime, start: datetime, now: datetime) -> None:
        """Accept late recording while rejecting pre-run, future and mixed-zone instants."""
        if any(moment.tzinfo is not None for moment in (value, start, now)):
            raise DomainError("utc_naive_required")
        if not start <= value <= now:
            raise DomainError("measurement_time_outside_run")


class SamplingSchedule:
    """Virtual slots avoid inserting unlimited empty rows during unattended production."""

    def __init__(self, start: datetime, interval_seconds: int) -> None:
        """Anchor slot zero at run start using a positive whole-second interval."""
        if type(interval_seconds) is not int or not 1 <= interval_seconds <= 2147483647:
            raise DomainError("invalid_interval")
        if start.tzinfo is not None:
            raise DomainError("utc_naive_required")
        self.start, self.interval = start, timedelta(seconds=interval_seconds)

    def due_count(self, until: datetime) -> int:
        """Count slot zero plus each interval reached, including an exact end boundary."""
        if until.tzinfo is not None or until < self.start:
            raise DomainError("invalid_schedule_time")
        return (until - self.start) // self.interval + 1

    def due_time(self, index: int) -> datetime:
        """Resolve a nonnegative slot index without rounding wall-clock times."""
        if type(index) is not int or index < 0:
            raise DomainError("invalid_slot")
        try:
            return self.start + index * self.interval
        except OverflowError as error:
            raise DomainError("invalid_slot") from error

    def validate_slot(self, index: int, measured_at: datetime, now: datetime) -> None:
        """A reading may fill only the scheduled interval in which it was measured."""
        due = self.due_time(index)
        if index >= self.due_count(now) or not due <= measured_at < due + self.interval:
            raise DomainError("measurement_outside_slot")

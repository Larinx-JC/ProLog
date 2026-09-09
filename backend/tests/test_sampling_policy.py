"""Explicit Shanghai/UTC conversion, late recording and deterministic sampling windows."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.numeric import DomainError
from app.domain.sampling import ProductionTime, SamplingSchedule

START = datetime(2026, 9, 7, 16)


@pytest.mark.parametrize(
    "value", ["2026-09-08T00:00:00", "2026-09-08T00:00:00+08:00", "2026-09-07T16:00:00Z"]
)
def test_factory_inputs_normalize_to_same_utc_day_boundary(value: str) -> None:
    """Normalize local, offset and UTC forms without borrowing the workstation timezone."""
    assert ProductionTime.parse(value) == START
    assert ProductionTime.parse(value).tzinfo is None


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-08",
        "invalid timestamp data",
        "2026-13-08T00:00:00",
        "1991-04-14T02:30:00",
        "1991-09-15T01:30:00",
    ],
)
def test_invalid_or_historically_ambiguous_factory_time(value: str) -> None:
    """Reject malformed and historical DST-gap/fold local times instead of guessing."""
    with pytest.raises(DomainError):
        ProductionTime.parse(value)


def test_measurement_window_and_late_recording() -> None:
    """Allow delayed entry while keeping true measurement time inside the run's history."""
    now = START + timedelta(seconds=120)
    ProductionTime.validate(START, START, now)
    ProductionTime.validate(now, START, now)
    for value in (START - timedelta(seconds=1), now + timedelta(seconds=1)):
        with pytest.raises(DomainError, match="measurement_time_outside_run"):
            ProductionTime.validate(value, START, now)
    with pytest.raises(DomainError, match="utc_naive_required"):
        ProductionTime.validate(START.replace(tzinfo=UTC), START, now)


@pytest.mark.parametrize("seconds,expected", [(0, 1), (59, 1), (60, 2), (120, 3)])
def test_expected_samples_include_exact_due_boundary(seconds: int, expected: int) -> None:
    """Slot zero is due at start; subsequent whole intervals are counted exactly."""
    assert SamplingSchedule(START, 60).due_count(START + timedelta(seconds=seconds)) == expected


def test_slot_assignment_and_late_submission() -> None:
    """Late submission can fill its original interval, but cannot mask a different missing slot."""
    schedule = SamplingSchedule(START, 60)
    schedule.validate_slot(0, START + timedelta(seconds=59), START + timedelta(seconds=120))
    assert schedule.due_time(2) == START + timedelta(seconds=120)
    for slot, measured in ((0, START + timedelta(seconds=60)), (3, START), (-1, START)):
        with pytest.raises(DomainError):
            schedule.validate_slot(slot, measured, START + timedelta(seconds=120))


@pytest.mark.parametrize("interval", [0, -1, True, 1.5, 2147483648])
def test_reject_invalid_intervals(interval) -> None:
    """Reject invalid whole-second or out-of-storage-range scheduling intervals."""
    with pytest.raises(DomainError, match="invalid_interval"):
        SamplingSchedule(START, interval)

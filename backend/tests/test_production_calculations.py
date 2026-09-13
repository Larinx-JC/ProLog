"""Hand-calculated examples, alarms, absence and exact threshold boundaries."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from app.domain.measurements import AbnormalityDetector, MeasurementCalculator, Readings, Rules
from app.domain.numeric import AccuracyPolicy, DomainError

D = Decimal
POLICY = AccuracyPolicy()
RULES = Rules(D("100"), D("110"), D("90"), D("0.006"), D("0.008"))


def readings(points: tuple[str, ...], **extras) -> Readings:
    """Create exact synthetic four-point inputs with valid thickness and length."""
    return Readings(
        **{f"point_{i}": D(p) for i, p in enumerate(points, 1)},
        **dict(thickness=D("0.007"), meter_count=D("1"), **extras),
    )


@pytest.mark.parametrize(
    "points,average,target,uniformity",
    [
        (("100", "100", "100", "100"), "100.00", "0.00", "0.00"),
        (("110", "110", "110", "110"), "110.00", "10.00", "0.00"),
        (("97", "99", "101", "103"), "100.00", "3.00", "3.00"),
        (("98", "100", "100", "102"), "100.00", "2.00", "2.00"),
    ],
)
def test_calculator_distinguishes_target_from_uniformity(
    points, average, target, uniformity
) -> None:
    """Uniform wrong readings fail target checks; averaging cannot hide opposing errors."""
    result = MeasurementCalculator.calculate(readings(points), RULES, POLICY)
    assert result is not None
    assert result.average == D(average)
    assert result.target_deviation_percent == D(target)
    assert result.uniformity_percent == D(uniformity)


@pytest.mark.parametrize(
    "point,alarm", [("97.99", True), ("98", False), ("102", False), ("102.01", True)]
)
def test_exact_resistance_tolerance(point: str, alarm: bool) -> None:
    """Both target boundaries are inclusive without relying on rounded statistics."""
    codes = AbnormalityDetector.evaluate(readings((point, "100", "100", "100")), RULES, POLICY)
    assert bool(codes) is alarm


def test_rounded_percentage_cannot_hide_alarm() -> None:
    """2.004% displays as 2.00% yet still exceeds a 2.00% acceptance threshold."""
    rules = replace(RULES, standard_value=D("1000"), upper_limit=D("1100"), lower_limit=D("900"))
    row = readings(("1020.04", "1000", "1000", "1000"))
    with localcontext() as context:
        context.prec = 4
        result = MeasurementCalculator.calculate(row, rules, POLICY)
        assert result.target_deviation_percent == D("2.00")
        assert AbnormalityDetector.evaluate(row, rules, POLICY) == ("point_1:target_deviation",)
        assert context.prec == 4


def test_partial_reading_detects_alarm_without_inventing_statistics() -> None:
    """A present bad value raises an alarm even when other required fields are absent."""
    row = Readings(point_1=D("120"))
    assert MeasurementCalculator.calculate(row, RULES, POLICY) is None
    assert AbnormalityDetector.evaluate(row, RULES, POLICY) == (
        "point_1:target_deviation",
        "point_1:resistance_limit",
    )
    assert row.missing(RULES) == ("point_2", "point_3", "point_4", "meter_count", "thickness")


def test_zero_is_recorded_and_uniformity_with_zero_mean_is_undefined() -> None:
    """Zero readings are not missing; division by a zero mean never fabricates uniformity."""
    row = readings(("0", "0", "0", "0"))
    assert row.missing(RULES) == ()
    result = MeasurementCalculator.calculate(row, RULES, POLICY)
    assert result.average == 0 and result.uniformity_percent is None
    assert result.target_deviation_percent == D("100.00")


@pytest.mark.parametrize(
    "value,alarm", [("0.005", True), ("0.006", False), ("0.008", False), ("0.009", True)]
)
def test_thickness_boundaries(value: str, alarm: bool) -> None:
    """Three-place mm is checked exactly against inclusive snapshotted limits."""
    row = replace(readings(("100",) * 4), thickness=D(value))
    assert bool(AbnormalityDetector.evaluate(row, RULES, POLICY)) is alarm


def test_disabled_checks_and_optional_fields() -> None:
    """Disabled checks contribute no alarm; absent optional speed/thickness permit completion."""
    rules = replace(
        RULES,
        deviation_check_enabled=False,
        thickness_check_enabled=False,
        limits_check_enabled=False,
    )
    row = replace(readings(("150",) * 4), thickness=None)
    assert AbnormalityDetector.evaluate(row, rules, POLICY) == ()
    assert row.missing(rules) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"standard_value": D("0")},
        {"lower_limit": D("111")},
        {"thickness_min": D("0.009")},
        {"deviation_pct_threshold": D("-1")},
        {"limits_check_enabled": "false"},
    ],
)
def test_invalid_rule_sets_are_rejected(changes: dict) -> None:
    """Reject invalid rules even if a caller bypasses the material input parser."""
    with pytest.raises(DomainError):
        replace(RULES, **changes).validate(POLICY)

"""Exact resistance statistics and independent, snapshot-based alarm rules."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.domain.numeric import AccuracyPolicy, DomainError


@dataclass(frozen=True)
class Rules:
    """A complete material rule value object copied into a run at creation."""

    standard_value: Decimal
    upper_limit: Decimal
    lower_limit: Decimal
    thickness_min: Decimal
    thickness_max: Decimal
    deviation_pct_threshold: Decimal = Decimal("2.00")
    deviation_check_enabled: bool = True
    thickness_check_enabled: bool = True
    limits_check_enabled: bool = True

    def validate(self, policy: AccuracyPolicy) -> None:
        """Validate material input and policy compatibility without changing thresholds."""
        for name in ("standard_value", "upper_limit", "lower_limit"):
            policy.validate(getattr(self, name), "resistance", positive=name == "standard_value")
        for name in ("thickness_min", "thickness_max"):
            policy.validate(getattr(self, name), "thickness")
        policy.validate(self.deviation_pct_threshold, "result")
        if self.lower_limit > self.upper_limit or self.thickness_min > self.thickness_max:
            raise DomainError("invalid_rule_range")
        for value in (
            self.deviation_check_enabled,
            self.thickness_check_enabled,
            self.limits_check_enabled,
        ):
            if type(value) is not bool:
                raise DomainError("invalid_check_switch")


@dataclass(frozen=True)
class Readings:
    """Partial or complete input; absence is represented only by None."""

    point_1: Decimal | None = None
    point_2: Decimal | None = None
    point_3: Decimal | None = None
    point_4: Decimal | None = None
    thickness: Decimal | None = None
    meter_count: Decimal | None = None
    speed: Decimal | None = None

    @property
    def points(self) -> tuple[Decimal | None, ...]:
        """Return the four spatial points in their stable input order."""
        return (self.point_1, self.point_2, self.point_3, self.point_4)

    def validate(self, policy: AccuracyPolicy) -> None:
        """Validate every supplied physical value, including optional speed/thickness."""
        for value in self.points:
            if value is not None:
                policy.validate(value, "resistance")
        for value, group in (
            (self.thickness, "thickness"),
            (self.meter_count, "length"),
            (self.speed, "speed"),
        ):
            if value is not None:
                policy.validate(value, group)

    def missing(self, rules: Rules) -> tuple[str, ...]:
        """Require four resistance points, length, and thickness when its check is enabled."""
        names = [f"point_{i}" for i, value in enumerate(self.points, 1) if value is None]
        if self.meter_count is None:
            names.append("meter_count")
        if rules.thickness_check_enabled and self.thickness is None:
            names.append("thickness")
        return tuple(names)


@dataclass(frozen=True)
class Statistics:
    """Rounded stored results; alarm comparison never uses these rounded values."""

    average: Decimal
    max_target_deviation: Decimal
    target_deviation_percent: Decimal
    max_uniformity_deviation: Decimal
    uniformity_percent: Decimal | None


class MeasurementCalculator:
    """Compute all four-point statistics with a private high-precision context."""

    @staticmethod
    def calculate(readings: Readings, rules: Rules, policy: AccuracyPolicy) -> Statistics | None:
        """Return no final statistics until all four readings are actually present."""
        readings.validate(policy)
        rules.validate(policy)
        if any(point is None for point in readings.points):
            return None
        points = tuple(point for point in readings.points if point is not None)
        with localcontext() as context:
            context.prec = 60
            average = sum(points, Decimal(0)) / Decimal(4)
            target = max(abs(point - rules.standard_value) for point in points)
            uniformity = max(abs(point - average) for point in points)
            return Statistics(
                policy.round(average),
                policy.round(target),
                policy.round(target * 100 / rules.standard_value),
                policy.round(uniformity),
                policy.round(uniformity * 100 / average) if average else None,
            )


class AbnormalityDetector:
    """Evaluate enabled limits against observed points, even in an incomplete row."""

    @staticmethod
    def evaluate(readings: Readings, rules: Rules, policy: AccuracyPolicy) -> tuple[str, ...]:
        """Use exact cross-products so rounding a quotient cannot change an alarm boundary."""
        readings.validate(policy)
        rules.validate(policy)
        alarms: list[str] = []
        with localcontext() as context:
            context.prec = 60
            for i, point in enumerate(readings.points, 1):
                if point is None:
                    continue
                if rules.deviation_check_enabled and (
                    abs(point - rules.standard_value) * 100
                    > rules.standard_value * rules.deviation_pct_threshold
                ):
                    alarms.append(f"point_{i}:target_deviation")
                if (
                    rules.limits_check_enabled
                    and not rules.lower_limit <= point <= rules.upper_limit
                ):
                    alarms.append(f"point_{i}:resistance_limit")
            if rules.thickness_check_enabled and readings.thickness is not None:
                if not rules.thickness_min <= readings.thickness <= rules.thickness_max:
                    alarms.append("thickness:limit")
        return tuple(alarms)

"""Shared presentation rounding, independent of recording and alarm policies."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from app.domain.numeric import MAX_RESULT, ROUNDING_MODES, AccuracyPolicy, DomainError

RULE_QUANTITIES = {
    "standard_value": "resistance",
    "upper_limit": "resistance",
    "lower_limit": "resistance",
    "thickness_min": "thickness",
    "thickness_max": "thickness",
    "deviation_pct_threshold": "result",
}
MEASUREMENT_QUANTITIES = {
    **{f"point_{i}": "resistance" for i in range(1, 5)},
    "thickness": "thickness",
    "meter_count": "length",
    "speed": "speed",
    **{
        name: "result"
        for name in (
            "average_value",
            "max_deviation",
            "deviation_percent",
            "target_deviation",
            "target_deviation_percent",
        )
    },
}


@dataclass(frozen=True)
class DisplayFormatter:
    """Reuse validated precision choices without using input validation to round history."""

    precision: AccuracyPolicy

    def format(self, value: str | Decimal, quantity: str) -> str:
        """Round a display copy, allowing an output carry beyond the stored numeric capacity."""
        if not isinstance(value, (str, Decimal)) or (isinstance(value, str) and len(value) > 64):
            raise DomainError("invalid_display_value")
        try:
            number = Decimal(value)
        except InvalidOperation as error:
            raise DomainError("invalid_display_value") from error
        if not number.is_finite() or number.copy_abs() > MAX_RESULT:
            raise DomainError("invalid_display_value")
        with localcontext() as context:
            context.prec = 60
            rounded = number.quantize(
                self.precision.quantum(quantity), rounding=ROUNDING_MODES[self.precision.rounding]
            )
        return format(rounded.copy_abs() if rounded == 0 else rounded, "f")

    def project(self, values: Mapping[str, str | None], groups: Mapping[str, str]) -> dict:
        """Format named quantities only; preserve nulls and leave source data untouched."""
        return {
            name: self.format(value, group) if (value := values.get(name)) is not None else None
            for name, group in groups.items()
        }

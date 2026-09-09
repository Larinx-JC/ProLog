"""Exact decimal validation, configurable precision, and explicit rounding."""

import re
from dataclasses import dataclass, fields
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext


class DomainError(Exception):
    """A stable service rejection that must roll back the entire operation."""

    def __init__(self, code: str, status: int = 422) -> None:
        """Expose a public code without database or credential details."""
        super().__init__(code)
        self.code, self.status = code, status


ROUNDING_MODES = {"half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN}
MAX_QUANTITY = Decimal("99999999.999999")
MAX_RESULT = Decimal("999999999999999999.999999")
DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


@dataclass(frozen=True)
class AccuracyPolicy:
    """Immutable effective precision; persistence gives each policy a version ID."""

    resistance_places: int = 2
    thickness_places: int = 3
    speed_places: int = 2
    length_places: int = 2
    result_places: int = 2
    rounding: str = "half_up"

    def __post_init__(self) -> None:
        """Reject unsupported scales and rounding before any policy is persisted."""
        for name in (f.name for f in fields(self) if f.name.endswith("_places")):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 6:
                raise DomainError("invalid_precision")
        if not isinstance(self.rounding, str) or self.rounding not in ROUNDING_MODES:
            raise DomainError("invalid_rounding")

    def scale(self, quantity: str) -> int:
        """Resolve a known physical/result group without accepting arbitrary attributes."""
        if quantity not in {"resistance", "thickness", "speed", "length", "result"}:
            raise DomainError("unknown_quantity")
        return getattr(self, f"{quantity}_places")

    def quantum(self, quantity: str) -> Decimal:
        """Produce the exact smallest accepted step for the chosen quantity."""
        return Decimal(1).scaleb(-self.scale(quantity))

    def parse(self, value: str, quantity: str, *, positive: bool = False) -> Decimal:
        """Accept canonical decimal text without silent rounding or float conversion."""
        if not isinstance(value, str) or len(value) > 32 or not DECIMAL_PATTERN.fullmatch(value):
            raise DomainError("invalid_decimal")
        places = len(value.partition(".")[2])
        if places > self.scale(quantity):
            raise DomainError("excess_precision")
        number = Decimal(value)
        self.validate(number, quantity, positive=positive)
        return self.round(number, quantity)

    def validate(self, value: Decimal, quantity: str, *, positive: bool = False) -> None:
        """Check persisted exact values too, ignoring harmless storage padding zeros."""
        if not isinstance(value, Decimal) or not value.is_finite():
            raise DomainError("invalid_decimal")
        if value < 0 or value > MAX_QUANTITY or (positive and value == 0):
            raise DomainError("quantity_out_of_range")
        if self.round(value, quantity) != value:
            raise DomainError("excess_precision")

    def round(self, value: Decimal, quantity: str = "result") -> Decimal:
        """Round only an explicit output boundary using a private decimal context."""
        if not isinstance(value, Decimal) or not value.is_finite() or value.copy_abs() > MAX_RESULT:
            raise DomainError("result_out_of_range")
        with localcontext() as context:
            context.prec = 60
            result = value.quantize(self.quantum(quantity), rounding=ROUNDING_MODES[self.rounding])
            if result.copy_abs() > MAX_RESULT:
                raise DomainError("result_out_of_range")
            return result.copy_abs() if result == 0 else result

    def format(self, value: Decimal, quantity: str = "result") -> str:
        """Return canonical API/display text with the captured field's trailing zeros."""
        return format(self.round(value, quantity), "f")

"""Behavioral precision/rounding tests independent of SQL or UI implementation."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from app.domain.numeric import AccuracyPolicy, DomainError


@pytest.mark.parametrize(
    "value,quantity,expected",
    [
        ("12", "resistance", "12.00"),
        ("12.3", "resistance", "12.30"),
        ("0.006", "thickness", "0.006"),
        ("0.008", "thickness", "0.008"),
        ("0.00", "speed", "0.00"),
        ("1234.56", "length", "1234.56"),
    ],
)
def test_parse_and_serialize_exact_values(value: str, quantity: str, expected: str) -> None:
    """Preserve valid operator readings and their configured trailing zeros."""
    policy = AccuracyPolicy()
    result = policy.parse(value, quantity)
    assert isinstance(result, Decimal)
    assert policy.format(result, quantity) == expected


@pytest.mark.parametrize("value", ["12.345", "12.300", "0.001"])
def test_input_is_not_silently_rounded(value: str) -> None:
    """Reject excess input digits even where trailing zeros would preserve value."""
    with pytest.raises(DomainError, match="excess_precision"):
        AccuracyPolicy().parse(value, "resistance")


@pytest.mark.parametrize("value", [1.2, True, None, "NaN", "Infinity", "1e2", " 1", "01", "", "1."])
def test_reject_noncanonical_inputs(value: object) -> None:
    """Reject implicit conversion, binary floats, exponent syntax and invalid text."""
    with pytest.raises(DomainError, match="invalid_decimal"):
        AccuracyPolicy().parse(value, "resistance")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["-0.01", "100000000.00"])
def test_reject_negative_or_oversized_quantities(value: str) -> None:
    """Respect nonnegative physical input and the preserved eight-digit integer range."""
    with pytest.raises(DomainError, match="quantity_out_of_range"):
        AccuracyPolicy().parse(value, "resistance")


def test_positive_target_and_storage_padding() -> None:
    """Reject zero targets while accepting exact DB padding at the selected scale."""
    policy = AccuracyPolicy()
    with pytest.raises(DomainError, match="quantity_out_of_range"):
        policy.parse("0", "resistance", positive=True)
    policy.validate(Decimal("12.300000"), "resistance")
    with pytest.raises(DomainError, match="excess_precision"):
        policy.validate(Decimal("12.301000"), "resistance")


@pytest.mark.parametrize("places", [-1, 7, True, 2.5, "3"])
def test_invalid_precision_settings(places: object) -> None:
    """Only integer scales within the supported capacity are accepted."""
    with pytest.raises(DomainError, match="invalid_precision"):
        AccuracyPolicy(thickness_places=places)  # type: ignore[arg-type]


@pytest.mark.parametrize("places,value", [(0, "12"), (3, "12.345"), (6, "12.345678")])
def test_admin_selected_scales(places: int, value: str) -> None:
    """Use each configured scale for validation and serialization."""
    policy = AccuracyPolicy(resistance_places=places)
    assert policy.format(policy.parse(value, "resistance"), "resistance") == value


@pytest.mark.parametrize(
    "mode,value,expected",
    [
        ("half_up", "12.345", "12.35"),
        ("half_even", "12.345", "12.34"),
        ("half_even", "12.355", "12.36"),
        ("half_up", "-12.345", "-12.35"),
    ],
)
def test_rounding_modes(mode: str, value: str, expected: str) -> None:
    """Assert halfway cases rather than merely executing both rounding branches."""
    policy = AccuracyPolicy(rounding=mode)
    with localcontext() as context:
        context.prec = 3
        assert policy.format(Decimal(value)) == expected
        assert context.prec == 3


def test_invalid_modes_groups_and_values() -> None:
    """Reject invalid policy names, nonfinite values and result overflow explicitly."""
    with pytest.raises(DomainError, match="invalid_rounding"):
        replace(AccuracyPolicy(), rounding="truncate")
    with pytest.raises(DomainError, match="unknown_quantity"):
        AccuracyPolicy().scale("rounding")
    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("1e30")):
        with pytest.raises(DomainError):
            AccuracyPolicy().validate(value, "resistance")
        with pytest.raises(DomainError, match="result_out_of_range"):
            AccuracyPolicy().round(value)

from decimal import Decimal

import pytest

from app.money import original_amount_text, parse_rate, to_idr, validate_amount


def test_confirmed_currency_scales_and_conversion() -> None:
    assert original_amount_text(5000, "IDR") == "5000"
    assert original_amount_text(566, "USD") == "5.66"
    assert to_idr(566, "USD", Decimal("16000")) == 90_560


def test_rounds_each_transaction_half_up() -> None:
    assert to_idr(1, "USD", "150") == 2
    assert to_idr(1, "USD", "149") == 1
    assert to_idr(10**15, "USD", "16000.123") == 160_001_230_000_000_000


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "1"])
def test_rejects_nonpositive_or_noninteger_amounts(value: object) -> None:
    with pytest.raises(ValueError):
        validate_amount(value, "IDR")


def test_rejects_unknown_currency_and_bad_rates() -> None:
    with pytest.raises(ValueError):
        validate_amount(1, "EUR")
    for rate in (0, -1, "NaN", "Infinity", "bad"):
        with pytest.raises(ValueError):
            parse_rate(rate)

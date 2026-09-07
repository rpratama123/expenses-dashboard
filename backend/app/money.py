from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY_SCALES = {"IDR": 1, "USD": 100}


def validate_amount(amount_minor: object, currency: str) -> int:
    if currency not in CURRENCY_SCALES:
        raise ValueError(f"unsupported currency: {currency}")
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise ValueError("amount_minor must be a positive integer")
    return amount_minor


def original_amount_text(amount_minor: int, currency: str) -> str:
    validate_amount(amount_minor, currency)
    if currency == "IDR":
        return str(amount_minor)
    return f"{amount_minor // 100}.{amount_minor % 100:02d}"


def parse_rate(rate: object) -> Decimal:
    try:
        value = Decimal(str(rate))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid FX rate") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("FX rate must be finite and positive")
    return value


def to_idr(amount_minor: int, currency: str, rate: Decimal | str | None = None) -> int | None:
    validate_amount(amount_minor, currency)
    if currency == "IDR":
        return amount_minor
    if rate is None:
        return None
    converted = (Decimal(amount_minor) / CURRENCY_SCALES["USD"]) * parse_rate(rate)
    return int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

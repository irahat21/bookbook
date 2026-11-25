"""Money helpers (SRS 3.1: money is a float stored with 2 decimals).

Python's round() uses "banker's rounding" on exact halves and works on binary
floats, so round(0.125, 2) == 0.12 and round(2.675, 2) == 2.67. A shop rounds
half a cent UP, so every amount goes through Decimal with ROUND_HALF_UP
(ASSUMPTIONS A-19). Example: the VIP discount on $12.45 is $1.245 -> $1.25.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def cents(value) -> float:
    """Round to the cent, half up. str() first so 2.675 is read as typed, not as 2.67499..."""
    return float(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def parse_amount(text: str) -> float:
    """Parse a typed amount like '25', '25.5' or '$1,000.00'.
    ValueError if it is not a number or has more than 2 decimals (UC-07 E1)."""
    cleaned = str(text).strip().replace(",", "").lstrip("$").strip()
    try:
        d = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("Enter a valid amount") from None
    if not d.is_finite() or d.as_tuple().exponent < -2:
        raise ValueError("Enter a valid amount")
    return float(d)

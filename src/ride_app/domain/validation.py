"""Small core validators shared by entities and transport-independent commands."""

from datetime import datetime
from decimal import Decimal, DecimalException

from ride_app.domain.errors import DomainError


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise DomainError(code, message)


def clean_text(value: str, field: str, code: str = "INVALID_REQUEST") -> str:
    require(isinstance(value, str) and bool(value.strip()), code, f"{field} must not be empty.")
    return value.strip()


def normalized_code(value: str, field: str, code: str) -> str:
    return clean_text(value, field, code).upper()


def nonnegative_decimal(value: Decimal, field: str, code: str = "INVALID_AMOUNT") -> None:
    require(
        isinstance(value, Decimal) and value.is_finite() and value >= 0,
        code,
        f"{field} must be a finite, nonnegative Decimal.",
    )


def money(value: Decimal, field: str) -> None:
    nonnegative_decimal(value, field)
    try:
        exact_cents = value == value.quantize(Decimal("0.01"))
    except DecimalException as exc:
        raise DomainError(
            "INVALID_AMOUNT", f"{field} exceeds supported decimal precision."
        ) from exc
    require(exact_cents, "INVALID_AMOUNT", f"{field} must have at most two fractional digits.")


def aware_time(value: datetime, field: str) -> None:
    require(
        isinstance(value, datetime) and value.utcoffset() is not None,
        "INVALID_RIDE_STATE",
        f"{field} must be timezone-aware.",
    )

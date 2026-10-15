"""Small pure policy contracts with deterministic, interchangeable implementations."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from ride_app.domain.models import Ride
from ride_app.domain.validation import aware_time, nonnegative_decimal, require


@dataclass(frozen=True, slots=True)
class MarketConditions:
    demand: int
    supply: int

    def __post_init__(self) -> None:
        require(
            type(self.demand) is int
            and type(self.supply) is int
            and self.demand >= 0
            and self.supply >= 0,
            "INVALID_MARKET",
            "Demand and supply must be nonnegative counts.",
        )


class SurgePolicy(Protocol):
    def multiplier(self, market: MarketConditions) -> Decimal: ...


class NoSurgePolicy:
    def multiplier(self, market: MarketConditions) -> Decimal:
        return Decimal("1")


@dataclass(frozen=True, slots=True)
class DemandSupplySurgePolicy:
    """Linear excess-demand multiplier, capped; zero supply is safe mathematically."""

    maximum: Decimal = Decimal("3")
    sensitivity: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        nonnegative_decimal(self.maximum, "maximum surge", "INVALID_SURGE")
        nonnegative_decimal(self.sensitivity, "surge sensitivity", "INVALID_SURGE")
        require(
            1 <= self.maximum <= 100 and self.sensitivity <= 100,
            "INVALID_SURGE",
            "Maximum must be 1–100 and sensitivity 0–100.",
        )

    def multiplier(self, market: MarketConditions) -> Decimal:
        ratio = Decimal(market.demand) / Decimal(max(1, market.supply))
        return min(self.maximum, Decimal("1") + max(Decimal("0"), ratio - 1) * self.sensitivity)


class CancellationFeePolicy(Protocol):
    """Return a nonnegative fee using captured terms, without changing ride state."""

    def calculate(self, ride: Ride, cancelled_at: datetime) -> Decimal: ...


class GracePeriodCancellationPolicy:
    def calculate(self, ride: Ride, cancelled_at: datetime) -> Decimal:
        aware_time(cancelled_at, "cancelled_at")
        require(
            cancelled_at >= ride.started_at,
            "INVALID_RIDE_STATE",
            "Cancellation cannot precede booking.",
        )
        elapsed = (cancelled_at - ride.started_at).total_seconds()
        terms = ride.terms.cancellation_terms
        return Decimal("0.00") if elapsed <= terms.grace_seconds else terms.fee


class FreeCancellationPolicy:
    def calculate(self, ride: Ride, cancelled_at: datetime) -> Decimal:
        return Decimal("0.00")

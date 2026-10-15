"""Eligibility and fallback are separate from driver-ranking strategy."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ride_app.domain.errors import FeatureNotImplemented
from ride_app.domain.models import CarType, Driver, Location


def distance_km(origin: Location, destination: Location) -> float:
    """Haversine distance used for matching, never for billed trip distance."""
    raise FeatureNotImplemented("Geographic distance calculation")


class MatchingStrategy(Protocol):
    """Swappable ranking contract; implementations must not decide eligibility."""

    def select(self, candidates: Sequence[Driver], pickup: Location) -> Driver:
        """Rank already-eligible candidates; require a nonempty sequence."""
        ...


class NearestDriverStrategy:
    """Default ranking policy; geographic calculation is pending implementation."""

    def select(self, candidates: Sequence[Driver], pickup: Location) -> Driver:
        """Choose by distance, with a stable driver-ID tie-breaker."""
        raise FeatureNotImplemented("Nearest-driver ranking")


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Selected driver with pickup distance, distinct from the billed trip distance."""

    driver: Driver
    pickup_distance_km: float


class DriverMatcher:
    """Own availability, radius, and car-type fallback before invoking ranking."""

    def __init__(self, strategy: MatchingStrategy) -> None:
        self._strategy = strategy

    def match(
        self,
        drivers: Sequence[Driver],
        pickup: Location,
        requested_type: CarType,
        radius_km: float,
    ) -> MatchResult:
        """Filter availability/radius, prefer requested type, then permitted upgrade."""
        # Planned order: requested-type candidates first, then Hatchback-to-Sedan fallback.
        # Even a nearer Sedan must not displace an eligible requested Hatchback.
        raise FeatureNotImplemented("Driver eligibility and upgrade matching")

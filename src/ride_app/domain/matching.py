"""Eligibility and fallback are enforced before a pluggable ranking strategy runs."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Protocol

from ride_app.domain.models import CarType, Driver, Location
from ride_app.domain.validation import require

EARTH_RADIUS_KM = 6371.0088


def distance_km(origin: Location, destination: Location) -> float:
    """Haversine great-circle distance; this is not the billed trip distance."""
    lat1, lat2 = radians(origin.latitude), radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lng = radians(destination.longitude - origin.longitude)
    haversine = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2
    # Clamp round-off near antipodal points before evaluating the inverse sine.
    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, max(0.0, haversine))))


class MatchingStrategy(Protocol):
    """Rank eligible drivers only; eligibility rules are owned by DriverMatcher."""

    def select(self, candidates: Sequence[Driver], pickup: Location) -> Driver: ...


class NearestDriverStrategy:
    """Deterministic default ranking: shortest distance, then ascending driver ID."""

    def select(self, candidates: Sequence[Driver], pickup: Location) -> Driver:
        require(bool(candidates), "NO_DRIVER_AVAILABLE", "No eligible driver is available.")
        return min(
            candidates, key=lambda driver: (distance_km(pickup, driver.cab.location), driver.id)
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Selected driver and pickup distance, independent of completion distance."""

    driver: Driver
    pickup_distance_km: float


class DriverMatcher:
    def __init__(self, strategy: MatchingStrategy) -> None:
        self._strategy = strategy

    def match(
        self,
        drivers: Sequence[Driver],
        pickup: Location,
        requested_type: CarType,
        radius_km: float,
    ) -> MatchResult:
        require(
            isfinite(radius_km) and radius_km > 0,
            "INVALID_RADIUS",
            "Search radius must be finite and positive.",
        )
        require(isinstance(requested_type, CarType), "INVALID_CAR_TYPE", "Unsupported car type.")
        eligible = tuple(
            driver
            for driver in drivers
            if driver.is_available and distance_km(pickup, driver.cab.location) <= radius_km
        )
        candidates = tuple(driver for driver in eligible if driver.cab.car_type == requested_type)
        # An eligible Hatchback always takes precedence over even a nearer Sedan.
        if not candidates and requested_type == CarType.HATCHBACK:
            candidates = tuple(
                driver for driver in eligible if driver.cab.car_type == CarType.SEDAN
            )
        require(
            bool(candidates),
            "NO_DRIVER_AVAILABLE",
            "No eligible driver is available within radius.",
        )
        selected = self._strategy.select(candidates, pickup)
        require(selected in candidates, "INVALID_MATCH", "Strategy selected an ineligible driver.")
        return MatchResult(selected, distance_km(pickup, selected.cab.location))

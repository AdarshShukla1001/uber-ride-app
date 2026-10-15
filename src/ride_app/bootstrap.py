"""Composition root: create one independent application context per process/session."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ride_app.application.coupon_service import CouponService
from ride_app.application.ports import Clock, IdGenerator, RateCardCatalog
from ride_app.application.registration_service import RegistrationService
from ride_app.application.ride_service import RideService
from ride_app.domain.matching import DriverMatcher, MatchingStrategy, NearestDriverStrategy
from ride_app.domain.pricing import PricingEngine
from ride_app.infrastructure.configuration import ConfiguredRateCardCatalog, Settings
from ride_app.infrastructure.memory import (
    InMemoryCouponRepository,
    InMemoryDriverRepository,
    InMemoryRideRepository,
    InMemoryUserRepository,
    InProcessMutationGuard,
)


def utc_now() -> datetime:
    """Use timezone-aware UTC timestamps so ordering is independent of local settings."""
    return datetime.now(UTC)


def generate_id() -> str:
    """Default ID source; tests may inject predictable values instead."""
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class Application:
    """Public services exposed to adapters; storage stays behind application contracts."""

    registration: RegistrationService
    rides: RideService
    coupons: CouponService


def create_application(
    settings: Settings | None = None,
    *,
    clock: Clock = utc_now,
    new_id: IdGenerator = generate_id,
    matching_strategy: MatchingStrategy | None = None,
    rate_cards: RateCardCatalog | None = None,
) -> Application:
    """Wire fresh repositories and services without sharing state across contexts."""
    settings = settings if settings is not None else Settings()
    users = InMemoryUserRepository()
    drivers = InMemoryDriverRepository()
    rides = InMemoryRideRepository()
    coupons = InMemoryCouponRepository()
    # All services receive the same guard; per-service locks would not prevent races
    # between location updates, coupon changes, booking, and completion.
    guard = InProcessMutationGuard()

    return Application(
        registration=RegistrationService(users, drivers, guard, new_id),
        rides=RideService(
            users=users,
            drivers=drivers,
            rides=rides,
            coupons=coupons,
            matcher=DriverMatcher(
                matching_strategy if matching_strategy is not None else NearestDriverStrategy(),
            ),
            pricing=PricingEngine(),
            rate_cards=rate_cards if rate_cards is not None else ConfiguredRateCardCatalog(),
            guard=guard,
            clock=clock,
            new_id=new_id,
            search_radius_km=settings.search_radius_km,
        ),
        coupons=CouponService(coupons, guard),
    )

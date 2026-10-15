"""Narrow structural contracts; no concrete storage imports."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from ride_app.domain.models import CarType, Coupon, Driver, Location, RateCard, Ride, User
from ride_app.domain.policies import MarketConditions

# Callables allow deterministic time and IDs in tests without global monkeypatching.
type Clock = Callable[[], datetime]
type IdGenerator = Callable[[], str]


class UserRepository(Protocol):
    """User storage contract; save inserts or replaces a record by its ID."""

    def save(self, user: User) -> None: ...
    def find_by_id(self, user_id: str) -> User | None: ...


class DriverRepository(Protocol):
    """Driver lookup and storage; services coordinate uniqueness and assignment checks."""

    def save(self, driver: Driver) -> None: ...
    def find_by_id(self, driver_id: str) -> Driver | None: ...
    def find_available(self) -> tuple[Driver, ...]: ...
    def find_by_registration(self, registration_number: str) -> Driver | None: ...


class RideRepository(Protocol):
    """Canonical ride storage; histories are projections, not separate mutable copies."""

    def save(self, ride: Ride) -> None: ...
    def find_by_id(self, ride_id: str) -> Ride | None: ...
    def find_ongoing(self) -> tuple[Ride, ...]: ...
    def find_active_by_user(self, user_id: str) -> Ride | None: ...
    def find_by_user(self, user_id: str) -> tuple[Ride, ...]: ...
    def find_by_driver(self, driver_id: str) -> tuple[Ride, ...]: ...


class CouponRepository(Protocol):
    """Store catalog entries by normalized code, including deactivated entries."""

    def save(self, coupon: Coupon) -> None: ...
    def find_by_code(self, code: str) -> Coupon | None: ...


class RateCardCatalog(Protocol):
    """Resolve immutable rates by requested car type, including free-upgrade bookings."""

    def get_for(self, car_type: CarType) -> RateCard: ...


class MutationGuard(Protocol):
    """Coordinate state access in one process; this contract does not promise rollback."""

    def exclusive(self) -> AbstractContextManager[None]: ...


class MarketConditionsProvider(Protocol):
    """Read a local demand/supply snapshot before the current driver is reserved."""

    def snapshot(self, pickup: Location, requested_type: CarType) -> "MarketConditions": ...

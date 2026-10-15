"""Process-local repositories of immutable domain records.

Services coordinate multi-record reads and writes using the shared mutation guard.
Repositories do not claim transaction rollback or cross-process persistence.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

from ride_app.domain.models import Coupon, Driver, Ride, RideStatus, User


class InMemoryUserRepository:
    """Store immutable rider records; business validation belongs to the service."""

    def __init__(self) -> None:
        self._records: dict[str, User] = {}

    def save(self, user: User) -> None:
        self._records[user.id] = user

    def find_by_id(self, user_id: str) -> User | None:
        return self._records.get(user_id)


class InMemoryDriverRepository:
    """Store driver snapshots; callers coordinate availability checks with assignment."""

    def __init__(self) -> None:
        self._records: dict[str, Driver] = {}

    def save(self, driver: Driver) -> None:
        self._records[driver.id] = driver

    def find_by_id(self, driver_id: str) -> Driver | None:
        return self._records.get(driver_id)

    def find_available(self) -> tuple[Driver, ...]:
        return tuple(driver for driver in self._records.values() if driver.is_available)

    def find_by_registration(self, registration_number: str) -> Driver | None:
        """Expect an already-normalized number from the application layer."""
        return next(
            (d for d in self._records.values() if d.cab.registration_number == registration_number),
            None,
        )


class InMemoryRideRepository:
    """One source of ride state for lookup and both history views."""

    def __init__(self) -> None:
        self._records: dict[str, Ride] = {}

    def save(self, ride: Ride) -> None:
        self._records[ride.id] = ride

    def find_by_id(self, ride_id: str) -> Ride | None:
        return self._records.get(ride_id)

    def find_ongoing(self) -> tuple[Ride, ...]:
        return tuple(ride for ride in self._records.values() if ride.status == RideStatus.ONGOING)

    def find_active_by_user(self, user_id: str) -> Ride | None:
        return next(
            (
                r
                for r in self._records.values()
                if r.user_id == user_id and r.status == RideStatus.ONGOING
            ),
            None,
        )

    def find_by_user(self, user_id: str) -> tuple[Ride, ...]:
        return self._newest_first(r for r in self._records.values() if r.user_id == user_id)

    def find_by_driver(self, driver_id: str) -> tuple[Ride, ...]:
        return self._newest_first(r for r in self._records.values() if r.driver_id == driver_id)

    @staticmethod
    def _newest_first(rides: Iterator[Ride]) -> tuple[Ride, ...]:
        # Descending start time with ascending ID makes equal-time results deterministic.
        return tuple(sorted(rides, key=lambda r: (-r.started_at.timestamp(), r.id)))


class InMemoryCouponRepository:
    """Retain inactive coupons so deletion cannot permit accidental code reuse."""

    def __init__(self) -> None:
        self._records: dict[str, Coupon] = {}

    def save(self, coupon: Coupon) -> None:
        self._records[coupon.code] = coupon

    def find_by_code(self, code: str) -> Coupon | None:
        return self._records.get(code)


class InProcessMutationGuard:
    """Shared process-local lock; neither a database transaction nor a distributed lock."""

    def __init__(self) -> None:
        self._lock = RLock()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Release the lock on exit, including when the guarded operation raises."""
        with self._lock:
            yield

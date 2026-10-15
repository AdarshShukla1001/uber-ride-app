"""Coordinate booking and completion; calculation remains in domain policies."""

from ride_app.application.contracts import BookRideCommand, CompleteRideCommand
from ride_app.application.ports import (
    Clock,
    CouponRepository,
    DriverRepository,
    IdGenerator,
    MutationGuard,
    RateCardCatalog,
    RideRepository,
    UserRepository,
)
from ride_app.domain.matching import DriverMatcher
from ride_app.domain.models import BookingTerms, Ride, RideStatus
from ride_app.domain.pricing import PricingEngine
from ride_app.domain.validation import clean_text, require


class RideService:
    """Coordinate ride workflows across repositories and pure domain policies.

    The shared guard protects related state changes; injected time and IDs make
    workflow tests reproducible. All fallible validation precedes repository writes.
    """

    def __init__(
        self,
        users: UserRepository,
        drivers: DriverRepository,
        rides: RideRepository,
        coupons: CouponRepository,
        matcher: DriverMatcher,
        pricing: PricingEngine,
        rate_cards: RateCardCatalog,
        guard: MutationGuard,
        clock: Clock,
        new_id: IdGenerator,
        search_radius_km: float,
    ) -> None:
        self._users = users
        self._drivers = drivers
        self._rides = rides
        self._coupons = coupons
        self._matcher = matcher
        self._pricing = pricing
        self._rate_cards = rate_cards
        self._guard = guard
        self._clock = clock
        self._new_id = new_id
        self._search_radius_km = search_radius_km

    def book_ride(self, command: BookRideCommand) -> Ride:
        """Capture requested-type pricing and reserve one driver under the shared guard."""
        with self._guard.exclusive():
            require(
                self._users.find_by_id(command.user_id) is not None,
                "USER_NOT_FOUND",
                "User does not exist.",
            )
            require(
                self._rides.find_active_by_user(command.user_id) is None,
                "USER_ALREADY_ON_RIDE",
                "User already has an ongoing ride.",
            )
            coupon = None
            if command.coupon_code is not None:
                coupon = self._coupons.find_by_code(command.coupon_code)
                require(
                    coupon is not None and coupon.active,
                    "INVALID_COUPON",
                    "Coupon is missing or inactive.",
                )
            match = self._matcher.match(
                self._drivers.find_available(),
                command.pickup,
                command.requested_type,
                self._search_radius_km,
            )
            # Billing follows requested type even if matching assigned an upgraded car.
            terms = BookingTerms(
                rate_card=self._rate_cards.get_for(command.requested_type),
                coupon_terms=coupon.terms if coupon else None,
                coupon_code=coupon.code if coupon else None,
            )
            ride = Ride(
                id=self._new_id(),
                user_id=command.user_id,
                driver_id=match.driver.id,
                requested_type=command.requested_type,
                assigned_type=match.driver.cab.car_type,
                pickup=command.pickup,
                started_at=self._clock(),
                terms=terms,
            )
            require(
                self._rides.find_by_id(ride.id) is None,
                "DUPLICATE_ID",
                "Generated ride ID already exists.",
            )
            assigned = match.driver.assign_ride(ride.id)
            # Stage all validated replacements first. These in-memory writes have no
            # business validation or external IO; a future adapter needs transactions.
            self._rides.save(ride)
            self._drivers.save(assigned)
            return ride

    def complete_ride(self, command: CompleteRideCommand) -> Ride:
        """Complete once; repeats cannot move/release a driver on a subsequent ride."""
        with self._guard.exclusive():
            ride = self._require_ride(command.ride_id)
            if ride.status == RideStatus.COMPLETED:
                return ride
            driver = self._drivers.find_by_id(ride.driver_id)
            require(driver is not None, "DRIVER_NOT_FOUND", "Driver does not exist.")
            receipt = self._pricing.calculate(command.distance_km, ride.terms)
            completed = ride.complete(command.distance_km, command.dropoff, receipt, self._clock())
            released = driver.release_ride(ride.id).update_location(command.dropoff)
            self._rides.save(completed)
            self._drivers.save(released)
            return completed

    def _require_ride(self, ride_id: str) -> Ride:
        ride = self._rides.find_by_id(ride_id)
        require(ride is not None, "RIDE_NOT_FOUND", "Ride does not exist.")
        return ride

    def get_ride(self, ride_id: str) -> Ride:
        with self._guard.exclusive():
            return self._require_ride(clean_text(ride_id, "ride_id"))

    def get_user_history(self, user_id: str) -> tuple[Ride, ...]:
        user_id = clean_text(user_id, "user_id")
        with self._guard.exclusive():
            require(
                self._users.find_by_id(user_id) is not None,
                "USER_NOT_FOUND",
                "User does not exist.",
            )
            return self._rides.find_by_user(user_id)

    def get_driver_history(self, driver_id: str) -> tuple[Ride, ...]:
        driver_id = clean_text(driver_id, "driver_id")
        with self._guard.exclusive():
            require(
                self._drivers.find_by_id(driver_id) is not None,
                "DRIVER_NOT_FOUND",
                "Driver does not exist.",
            )
            return self._rides.find_by_driver(driver_id)

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
from ride_app.domain.errors import FeatureNotImplemented
from ride_app.domain.matching import DriverMatcher
from ride_app.domain.models import Ride
from ride_app.domain.pricing import PricingEngine


class RideService:
    """Coordinate ride workflows across repositories and pure domain policies.

    Methods remain scaffolded. The injected guard will protect related state changes;
    the injected clock and ID generator make future workflow tests reproducible.
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
        """Capture requested-type pricing and atomically reserve a driver."""
        # Planned: validate, match, capture terms, then stage ride and driver replacements
        # within one shared guard. A lock alone does not undo a partially applied write.
        raise FeatureNotImplemented("Ride booking")

    def complete_ride(self, command: CompleteRideCommand) -> Ride:
        """Persist a receipt and release the driver once; repeats return stored state."""
        # Check for an existing receipt before releasing or relocating a driver again:
        # that driver may already be assigned to a subsequent ride.
        raise FeatureNotImplemented("Ride completion")

    def get_ride(self, ride_id: str) -> Ride:
        """Planned: return the canonical record or raise a stable not-found error."""
        raise FeatureNotImplemented("Ride lookup")

    def get_user_history(self, user_id: str) -> tuple[Ride, ...]:
        """Planned: validate the user, then return ongoing and completed rides newest first."""
        raise FeatureNotImplemented("User ride history")

    def get_driver_history(self, driver_id: str) -> tuple[Ride, ...]:
        """Planned: validate the driver, then query the same records used by rider history."""
        raise FeatureNotImplemented("Driver ride history")

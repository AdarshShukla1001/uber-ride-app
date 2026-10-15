"""Domain data structures; lifecycle validation will accompany use-case implementation.

Immutable records allow services to stage replacement values before committing them.
Money and billed distance use Decimal; coordinates use floats for geographic math.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class CarType(StrEnum):
    """Vehicle categories used for matching and selecting a billing rate card."""

    HATCHBACK = "hatchback"
    SEDAN = "sedan"


class RideStatus(StrEnum):
    """Minimal lifecycle: booking starts a ride and completion ends it."""

    ONGOING = "ongoing"
    COMPLETED = "completed"


class DiscountType(StrEnum):
    """Only expose discount kinds supported by the planned initial release."""

    PERCENTAGE = "percentage"


@dataclass(frozen=True, slots=True)
class Location:
    """Geographic coordinates in degrees; core range validation is still pending."""

    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class User:
    """Rider identity; ride history is queried from canonical ride records."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Cab:
    """Vehicle details and latest location, owned by one driver in this exercise."""

    registration_number: str
    car_type: CarType
    location: Location


@dataclass(frozen=True, slots=True)
class Driver:
    """Driver identity and assignment; lifecycle changes will create replacements."""

    id: str
    name: str
    cab: Cab
    active_ride_id: str | None = None

    @property
    def is_available(self) -> bool:
        """Derive availability to avoid a flag contradicting the active assignment."""
        return self.active_ride_id is None


@dataclass(frozen=True, slots=True)
class PricingTier:
    """Marginal rate up to an absolute km boundary; None denotes the final open tier."""

    upper_bound_km: Decimal | None
    rate_per_km: Decimal


@dataclass(frozen=True, slots=True)
class RateCard:
    """Versioned rates; immutable tiers can be retained safely by a booked ride."""

    version: str
    car_type: CarType
    minimum_fare: Decimal
    tiers: tuple[PricingTier, ...]


@dataclass(frozen=True, slots=True)
class CouponTerms:
    """Captured discount definition, independent of the coupon's active flag."""

    discount_type: DiscountType
    value: Decimal


@dataclass(frozen=True, slots=True)
class Coupon:
    """Coupon catalog entry; future deletion deactivates it for new bookings only."""

    code: str
    terms: CouponTerms
    active: bool = True


@dataclass(frozen=True, slots=True)
class BookingTerms:
    """Booking-time rates and coupon terms, insulated from later catalog changes."""

    rate_card: RateCard
    coupon_terms: CouponTerms | None = None
    coupon_code: str | None = None


@dataclass(frozen=True, slots=True)
class FareBreakdown:
    """Receipt components intended to reconcile as charge + adjustment - discount."""

    distance_charge: Decimal
    minimum_fare_adjustment: Decimal
    discount: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class Ride:
    """Canonical trip record shared by rider history, driver history, and receipts.

    Requested type determines billing even when the assigned vehicle is an upgrade.
    Completion fields remain absent until a future validated completion operation.
    """

    id: str
    user_id: str
    driver_id: str
    requested_type: CarType
    assigned_type: CarType
    pickup: Location
    started_at: datetime
    terms: BookingTerms
    status: RideStatus = RideStatus.ONGOING
    dropoff: Location | None = None
    completed_at: datetime | None = None
    distance_km: Decimal | None = None
    receipt: FareBreakdown | None = None

    @property
    def is_upgrade(self) -> bool:
        """Identify a type change; the matcher must enforce allowed upgrade direction."""
        return self.requested_type != self.assigned_type

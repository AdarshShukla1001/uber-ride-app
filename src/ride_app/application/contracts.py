"""Framework-independent inputs shared by CLI and API."""

from dataclasses import dataclass
from decimal import Decimal

from ride_app.domain.models import CarType, CouponTerms, Location


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    """Transport-independent input; core name validation is pending."""

    name: str


@dataclass(frozen=True, slots=True)
class RegisterDriverCommand:
    """Create a driver with the single cab and initial location required for matching."""

    name: str
    registration_number: str
    car_type: CarType
    location: Location


@dataclass(frozen=True, slots=True)
class BookRideCommand:
    """Request a car category; the service selects the actual driver and captures terms."""

    user_id: str
    pickup: Location
    requested_type: CarType
    coupon_code: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteRideCommand:
    """Trusted exercise trip distance and drop-off, supplied separately from matching."""

    ride_id: str
    distance_km: Decimal
    dropoff: Location


@dataclass(frozen=True, slots=True)
class AddCouponCommand:
    """Create a catalog coupon; normalization and duplicate checks belong in the core."""

    code: str
    terms: CouponTerms

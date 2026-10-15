"""Validated, framework-independent inputs shared by CLI and API."""

from dataclasses import dataclass
from decimal import Decimal

from ride_app.domain.models import CarType, CouponTerms, Location
from ride_app.domain.validation import clean_text, nonnegative_decimal, normalized_code, require


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    """Reject invalid names regardless of which transport invokes registration."""

    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", clean_text(self.name, "name", "INVALID_NAME"))


@dataclass(frozen=True, slots=True)
class RegisterDriverCommand:
    """Create a driver with a cab and valid initial location."""

    name: str
    registration_number: str
    car_type: CarType
    location: Location
    rating: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", clean_text(self.name, "name", "INVALID_NAME"))
        object.__setattr__(
            self,
            "registration_number",
            normalized_code(
                self.registration_number,
                "registration_number",
                "INVALID_REGISTRATION",
            ),
        )
        if self.rating is not None:
            nonnegative_decimal(self.rating, "rating", "INVALID_RATING")
            require(self.rating <= 5, "INVALID_RATING", "Rating must be between 0 and 5.")
        require(isinstance(self.car_type, CarType), "INVALID_CAR_TYPE", "Unsupported car type.")
        require(isinstance(self.location, Location), "INVALID_LOCATION", "A location is required.")


@dataclass(frozen=True, slots=True)
class BookRideCommand:
    """Requested category and optional coupon; assignment remains a service decision."""

    user_id: str
    pickup: Location
    requested_type: CarType
    coupon_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", clean_text(self.user_id, "user_id"))
        require(isinstance(self.pickup, Location), "INVALID_LOCATION", "Pickup is required.")
        require(
            isinstance(self.requested_type, CarType), "INVALID_CAR_TYPE", "Unsupported car type."
        )
        if self.coupon_code is not None:
            object.__setattr__(
                self,
                "coupon_code",
                normalized_code(
                    self.coupon_code,
                    "coupon_code",
                    "INVALID_COUPON",
                ),
            )


@dataclass(frozen=True, slots=True)
class CompleteRideCommand:
    """Trusted exercise distance; repeat requests still require valid completion inputs."""

    ride_id: str
    distance_km: Decimal
    dropoff: Location

    def __post_init__(self) -> None:
        object.__setattr__(self, "ride_id", clean_text(self.ride_id, "ride_id"))
        nonnegative_decimal(self.distance_km, "distance_km", "INVALID_DISTANCE")
        require(isinstance(self.dropoff, Location), "INVALID_LOCATION", "Drop-off is required.")


@dataclass(frozen=True, slots=True)
class AddCouponCommand:
    """Normalized catalog code and validated discount terms."""

    code: str
    terms: CouponTerms

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalized_code(self.code, "code", "INVALID_COUPON"))
        require(isinstance(self.terms, CouponTerms), "INVALID_COUPON", "Coupon terms are required.")


@dataclass(frozen=True, slots=True)
class CancelRideCommand:
    ride_id: str
    reason: str = "Cancelled by rider"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ride_id", clean_text(self.ride_id, "ride_id"))
        object.__setattr__(self, "reason", clean_text(self.reason, "reason"))

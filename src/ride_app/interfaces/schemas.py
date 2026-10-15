"""HTTP request shapes; domain validation must also protect non-HTTP callers."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from ride_app.domain.models import CarType, DiscountType, Location, RideStatus

type MoneyAmount = Annotated[
    Decimal, PlainSerializer(lambda value: format(value, ".2f"), return_type=str)
]


class RequestModel(BaseModel):
    """Reject unknown HTTP fields and trim text before field-level validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocationRequest(RequestModel):
    """Validate HTTP coordinates before constructing a validated core Location."""

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)

    def to_domain(self) -> Location:
        """Convert the HTTP model so Pydantic objects do not enter application services."""
        return Location(latitude=self.latitude, longitude=self.longitude)


class RegisterUserRequest(RequestModel):
    """HTTP shape for rider registration, separate from the shared command object."""

    name: str = Field(min_length=1)


class RegisterDriverRequest(RequestModel):
    """Register a driver and the single cab used by this exercise's matching model."""

    name: str = Field(min_length=1)
    registration_number: str = Field(min_length=1)
    car_type: CarType
    location: LocationRequest


class BookRideRequest(RequestModel):
    """Express requested type; actual assignment and upgrade are service decisions."""

    user_id: str = Field(min_length=1)
    pickup: LocationRequest
    requested_type: CarType
    coupon_code: str | None = Field(default=None, min_length=1)


class CompleteRideRequest(RequestModel):
    """Accept trusted trip distance, not a distance inferred from pickup/drop-off."""

    distance_km: Decimal = Field(ge=0, allow_inf_nan=False)
    dropoff: LocationRequest


class AddCouponRequest(RequestModel):
    """Initial HTTP contract supports percentage coupons only."""

    code: str = Field(min_length=1)
    percentage: Decimal = Field(gt=0, le=100, allow_inf_nan=False)


# Output schemas keep HTTP contracts explicit while services return domain records.
# Fare amounts use fixed paise; rate and distance Decimals retain their precision.
class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LocationResponse(ResponseModel):
    latitude: float
    longitude: float


class UserResponse(ResponseModel):
    id: str
    name: str


class CabResponse(ResponseModel):
    registration_number: str
    car_type: CarType
    location: LocationResponse


class DriverResponse(ResponseModel):
    id: str
    name: str
    cab: CabResponse
    active_ride_id: str | None
    is_available: bool


class PricingTierResponse(ResponseModel):
    upper_bound_km: Decimal | None
    rate_per_km: Decimal


class RateCardResponse(ResponseModel):
    version: str
    car_type: CarType
    minimum_fare: MoneyAmount
    tiers: tuple[PricingTierResponse, ...]


class CouponTermsResponse(ResponseModel):
    discount_type: DiscountType
    value: Decimal


class CouponResponse(ResponseModel):
    code: str
    active: bool
    terms: CouponTermsResponse


class BookingTermsResponse(ResponseModel):
    rate_card: RateCardResponse
    coupon_terms: CouponTermsResponse | None
    coupon_code: str | None


class FareResponse(ResponseModel):
    distance_charge: MoneyAmount
    minimum_fare_adjustment: MoneyAmount
    discount: MoneyAmount
    total: MoneyAmount


class RideResponse(ResponseModel):
    id: str
    user_id: str
    driver_id: str
    requested_type: CarType
    assigned_type: CarType
    is_upgrade: bool
    status: RideStatus
    pickup: LocationResponse
    started_at: datetime
    terms: BookingTermsResponse
    dropoff: LocationResponse | None
    completed_at: datetime | None
    distance_km: Decimal | None
    receipt: FareResponse | None

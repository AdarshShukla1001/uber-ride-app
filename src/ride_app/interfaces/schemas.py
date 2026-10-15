"""HTTP request shapes; domain validation must also protect non-HTTP callers."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ride_app.domain.models import CarType, Location


class RequestModel(BaseModel):
    """Reject unknown HTTP fields and trim text before field-level validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocationRequest(RequestModel):
    """Validate HTTP coordinates; CLI protection still requires pending core validation."""

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

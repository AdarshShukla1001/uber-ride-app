"""Validated immutable records; lifecycle operations stage replacement values.

Money and billed distance use Decimal. Coordinates use floats for geographic math.
No domain model depends on HTTP, CLI parsing, or a particular storage adapter.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import Self

from ride_app.domain.validation import (
    aware_time,
    clean_text,
    money,
    nonnegative_decimal,
    normalized_code,
    require,
)


class CarType(StrEnum):
    """Vehicle categories used for matching and selecting a billing rate card."""

    HATCHBACK = "hatchback"
    SEDAN = "sedan"


class RideStatus(StrEnum):
    """Booking starts a ride; completion ends it."""

    ONGOING = "ongoing"
    COMPLETED = "completed"


class DiscountType(StrEnum):
    """Only expose discount kinds supported by the initial release."""

    PERCENTAGE = "percentage"


@dataclass(frozen=True, slots=True)
class Location:
    """Finite geographic coordinates in degrees, validated for every adapter."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        for value, bound, name in (
            (self.latitude, 90, "latitude"),
            (self.longitude, 180, "longitude"),
        ):
            require(
                type(value) in (int, float) and isfinite(value) and -bound <= value <= bound,
                "INVALID_LOCATION",
                f"{name} must be finite and between {-bound} and {bound}.",
            )


@dataclass(frozen=True, slots=True)
class User:
    """Rider identity; history comes from canonical ride records."""

    id: str
    name: str

    def __post_init__(self) -> None:
        clean_text(self.id, "user_id")
        object.__setattr__(self, "name", clean_text(self.name, "name", "INVALID_NAME"))


@dataclass(frozen=True, slots=True)
class Cab:
    """One driver's vehicle and latest location."""

    registration_number: str
    car_type: CarType
    location: Location

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registration_number",
            normalized_code(
                self.registration_number,
                "registration_number",
                "INVALID_REGISTRATION",
            ),
        )
        require(isinstance(self.car_type, CarType), "INVALID_CAR_TYPE", "Unsupported car type.")
        require(isinstance(self.location, Location), "INVALID_LOCATION", "A location is required.")


@dataclass(frozen=True, slots=True)
class Driver:
    """Assignment is the single source of availability; transitions return replacements."""

    id: str
    name: str
    cab: Cab
    active_ride_id: str | None = None

    def __post_init__(self) -> None:
        clean_text(self.id, "driver_id")
        object.__setattr__(self, "name", clean_text(self.name, "name", "INVALID_NAME"))
        require(isinstance(self.cab, Cab), "INVALID_REGISTRATION", "A cab is required.")
        if self.active_ride_id is not None:
            clean_text(self.active_ride_id, "active_ride_id")

    @property
    def is_available(self) -> bool:
        return self.active_ride_id is None

    def assign_ride(self, ride_id: str) -> Self:
        require(self.is_available, "DRIVER_ALREADY_ON_RIDE", "Driver already has an ongoing ride.")
        return replace(self, active_ride_id=clean_text(ride_id, "ride_id"))

    def release_ride(self, ride_id: str) -> Self:
        require(self.active_ride_id == ride_id, "INVALID_RIDE_STATE", "Driver assignment differs.")
        return replace(self, active_ride_id=None)

    def update_location(self, location: Location) -> Self:
        return replace(self, cab=replace(self.cab, location=location))


@dataclass(frozen=True, slots=True)
class PricingTier:
    """Marginal rate up to an absolute km boundary; None denotes the final open tier."""

    upper_bound_km: Decimal | None
    rate_per_km: Decimal

    def __post_init__(self) -> None:
        nonnegative_decimal(self.rate_per_km, "rate_per_km", "INVALID_RATE_CARD")
        if self.upper_bound_km is not None:
            nonnegative_decimal(self.upper_bound_km, "upper_bound_km", "INVALID_RATE_CARD")
            require(self.upper_bound_km > 0, "INVALID_RATE_CARD", "Tier bounds must be positive.")


@dataclass(frozen=True, slots=True)
class RateCard:
    """Immutable rate data, captured at booking instead of looked up at completion."""

    version: str
    car_type: CarType
    minimum_fare: Decimal
    tiers: tuple[PricingTier, ...]

    def __post_init__(self) -> None:
        clean_text(self.version, "version", "INVALID_RATE_CARD")
        require(isinstance(self.car_type, CarType), "INVALID_CAR_TYPE", "Unsupported car type.")
        money(self.minimum_fare, "minimum_fare")
        require(
            isinstance(self.tiers, tuple) and bool(self.tiers),
            "INVALID_RATE_CARD",
            "Rate cards require an immutable nonempty tier sequence.",
        )
        previous = Decimal("0")
        for index, tier in enumerate(self.tiers):
            require(isinstance(tier, PricingTier), "INVALID_RATE_CARD", "Invalid tier.")
            if tier.upper_bound_km is None:
                require(
                    index == len(self.tiers) - 1,
                    "INVALID_RATE_CARD",
                    "Only the final tier may be unbounded.",
                )
            else:
                require(
                    tier.upper_bound_km > previous,
                    "INVALID_RATE_CARD",
                    "Tier bounds must be strictly increasing.",
                )
                previous = tier.upper_bound_km
        require(
            self.tiers[-1].upper_bound_km is None,
            "INVALID_RATE_CARD",
            "The final tier must cover all remaining distance.",
        )


@dataclass(frozen=True, slots=True)
class CouponTerms:
    """Discount definition independent of catalog availability."""

    discount_type: DiscountType
    value: Decimal

    def __post_init__(self) -> None:
        require(
            self.discount_type is DiscountType.PERCENTAGE,
            "INVALID_COUPON",
            "Unsupported discount type.",
        )
        nonnegative_decimal(self.value, "coupon value", "INVALID_COUPON")
        require(
            0 < self.value <= 100, "INVALID_COUPON", "Percentage must be above 0 and at most 100."
        )


@dataclass(frozen=True, slots=True)
class Coupon:
    """Catalog entry; deactivation leaves existing booking snapshots usable."""

    code: str
    terms: CouponTerms
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalized_code(self.code, "code", "INVALID_COUPON"))
        require(isinstance(self.terms, CouponTerms), "INVALID_COUPON", "Coupon terms are required.")
        require(type(self.active) is bool, "INVALID_COUPON", "active must be a boolean.")

    def deactivate(self) -> Self:
        return replace(self, active=False)


@dataclass(frozen=True, slots=True)
class BookingTerms:
    """Booking-time pricing; no mutable collection is retained in the snapshot."""

    rate_card: RateCard
    coupon_terms: CouponTerms | None = None
    coupon_code: str | None = None

    def __post_init__(self) -> None:
        require(
            isinstance(self.rate_card, RateCard), "INVALID_RATE_CARD", "A rate card is required."
        )
        require(
            (self.coupon_terms is None) == (self.coupon_code is None),
            "INVALID_COUPON",
            "Coupon code and terms must be captured together.",
        )
        if self.coupon_code is not None:
            require(isinstance(self.coupon_terms, CouponTerms), "INVALID_COUPON", "Invalid terms.")
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
class FareBreakdown:
    """Receipt amounts reconcile exactly and are nonnegative whole paise."""

    distance_charge: Decimal
    minimum_fare_adjustment: Decimal
    discount: Decimal
    total: Decimal

    def __post_init__(self) -> None:
        for field in ("distance_charge", "minimum_fare_adjustment", "discount", "total"):
            money(getattr(self, field), field)
        require(
            self.distance_charge + self.minimum_fare_adjustment - self.discount == self.total,
            "INVALID_AMOUNT",
            "Receipt components do not reconcile.",
        )


@dataclass(frozen=True, slots=True)
class Ride:
    """Canonical trip record; requested type determines billing even for free upgrades."""

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

    def __post_init__(self) -> None:
        for field in ("id", "user_id", "driver_id"):
            clean_text(getattr(self, field), field)
        require(
            isinstance(self.requested_type, CarType) and isinstance(self.assigned_type, CarType),
            "INVALID_CAR_TYPE",
            "Unsupported car type.",
        )
        require(
            self.requested_type == self.assigned_type
            or (self.requested_type == CarType.HATCHBACK and self.assigned_type == CarType.SEDAN),
            "INVALID_RIDE_STATE",
            "Only Hatchback-to-Sedan upgrades are supported.",
        )
        require(isinstance(self.pickup, Location), "INVALID_LOCATION", "Pickup is required.")
        require(
            isinstance(self.terms, BookingTerms), "INVALID_RATE_CARD", "Booking terms required."
        )
        require(
            self.terms.rate_card.car_type == self.requested_type,
            "INVALID_RATE_CARD",
            "Billing rates must match the requested type.",
        )
        aware_time(self.started_at, "started_at")
        require(isinstance(self.status, RideStatus), "INVALID_RIDE_STATE", "Invalid ride status.")
        completion = (self.dropoff, self.completed_at, self.distance_km, self.receipt)
        if self.status == RideStatus.ONGOING:
            require(
                all(item is None for item in completion),
                "INVALID_RIDE_STATE",
                "Ongoing rides cannot contain completion fields.",
            )
        else:
            require(
                all(item is not None for item in completion),
                "INVALID_RIDE_STATE",
                "Completed rides require all completion fields.",
            )
            require(isinstance(self.dropoff, Location), "INVALID_LOCATION", "Invalid drop-off.")
            aware_time(self.completed_at, "completed_at")
            require(
                self.completed_at >= self.started_at,
                "INVALID_RIDE_STATE",
                "Completion cannot precede booking.",
            )
            nonnegative_decimal(self.distance_km, "distance_km", "INVALID_DISTANCE")
            require(isinstance(self.receipt, FareBreakdown), "INVALID_AMOUNT", "Receipt required.")

    @property
    def is_upgrade(self) -> bool:
        return self.requested_type != self.assigned_type

    def complete(
        self,
        distance: Decimal,
        dropoff: Location,
        receipt: FareBreakdown,
        time: datetime,
    ) -> Self:
        require(
            self.status == RideStatus.ONGOING, "INVALID_RIDE_STATE", "Ride is already completed."
        )
        return replace(
            self,
            status=RideStatus.COMPLETED,
            distance_km=distance,
            dropoff=dropoff,
            receipt=receipt,
            completed_at=time,
        )

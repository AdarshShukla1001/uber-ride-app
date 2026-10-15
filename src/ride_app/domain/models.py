"""Validated immutable records; lifecycle operations stage replacement values.

Money and billed distance use Decimal. Coordinates use floats for geographic math.
No domain model depends on HTTP, CLI parsing, or a particular storage adapter.
"""

from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
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
    SUV = "suv"


class RideStatus(StrEnum):
    """Booking starts a ride; completion and cancellation are terminal states."""

    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DiscountType(StrEnum):
    """Supported discount kinds; each has validation and calculation behavior."""

    PERCENTAGE = "percentage"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class UpgradeRules:
    """Ordered allowed assignments; exact type always has first priority."""

    routes: tuple[tuple[CarType, tuple[CarType, ...]], ...] = (
        (CarType.HATCHBACK, (CarType.HATCHBACK, CarType.SEDAN)),
        (CarType.SEDAN, (CarType.SEDAN,)),
        (CarType.SUV, (CarType.SUV,)),
    )

    def __post_init__(self) -> None:
        require(isinstance(self.routes, tuple), "INVALID_UPGRADES", "Routes must be immutable.")
        seen = set()
        for route in self.routes:
            require(
                isinstance(route, tuple) and len(route) == 2,
                "INVALID_UPGRADES",
                "Each route must be an immutable pair.",
            )
            requested, allowed = route
            require(
                isinstance(requested, CarType) and requested not in seen,
                "INVALID_UPGRADES",
                "Each car type needs one route.",
            )
            require(
                isinstance(allowed, tuple)
                and bool(allowed)
                and allowed[0] == requested
                and all(isinstance(kind, CarType) for kind in allowed)
                and len(set(allowed)) == len(allowed),
                "INVALID_UPGRADES",
                "Routes must start with requested type and have no duplicates.",
            )
            seen.add(requested)
        require(seen == set(CarType), "INVALID_UPGRADES", "Routes must cover every car type.")

    def types_for(self, requested: CarType) -> tuple[CarType, ...]:
        return next(allowed for kind, allowed in self.routes if kind == requested)


@dataclass(frozen=True, slots=True)
class CancellationTerms:
    """Booking-time fee terms; free through the inclusive grace period."""

    grace_seconds: int = 120
    fee: Decimal = Decimal("20.00")

    def __post_init__(self) -> None:
        require(
            type(self.grace_seconds) is int and self.grace_seconds >= 0,
            "INVALID_CANCELLATION",
            "Grace period must be nonnegative whole seconds.",
        )
        money(self.fee, "cancellation fee")


@dataclass(frozen=True, slots=True)
class CancellationDetails:
    cancelled_at: datetime
    fee: Decimal
    reason: str

    def __post_init__(self) -> None:
        aware_time(self.cancelled_at, "cancelled_at")
        money(self.fee, "cancellation fee")
        object.__setattr__(self, "reason", clean_text(self.reason, "reason"))


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
    rating: Decimal | None = None

    def __post_init__(self) -> None:
        clean_text(self.id, "driver_id")
        object.__setattr__(self, "name", clean_text(self.name, "name", "INVALID_NAME"))
        require(isinstance(self.cab, Cab), "INVALID_REGISTRATION", "A cab is required.")
        if self.rating is not None:
            nonnegative_decimal(self.rating, "rating", "INVALID_RATING")
            require(self.rating <= 5, "INVALID_RATING", "Rating must be between 0 and 5.")
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
            isinstance(self.discount_type, DiscountType),
            "INVALID_COUPON",
            "Unsupported discount type.",
        )
        nonnegative_decimal(self.value, "coupon value", "INVALID_COUPON")
        require(self.value > 0, "INVALID_COUPON", "Discount must be positive.")
        if self.discount_type == DiscountType.PERCENTAGE:
            require(self.value <= 100, "INVALID_COUPON", "Percentage must be at most 100.")
        else:
            money(self.value, "flat discount")


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
    surge_multiplier: Decimal = Decimal("1")
    cancellation_terms: CancellationTerms = dataclass_field(default_factory=CancellationTerms)
    allowed_assignment_types: tuple[CarType, ...] | None = None

    def __post_init__(self) -> None:
        require(
            isinstance(self.rate_card, RateCard), "INVALID_RATE_CARD", "A rate card is required."
        )
        nonnegative_decimal(self.surge_multiplier, "surge multiplier", "INVALID_SURGE")
        require(self.surge_multiplier >= 1, "INVALID_SURGE", "Surge cannot be below one.")
        require(
            isinstance(self.cancellation_terms, CancellationTerms),
            "INVALID_CANCELLATION",
            "Cancellation terms are required.",
        )
        if self.allowed_assignment_types is None:
            object.__setattr__(
                self, "allowed_assignment_types", UpgradeRules().types_for(self.rate_card.car_type)
            )
        require(
            isinstance(self.allowed_assignment_types, tuple)
            and bool(self.allowed_assignment_types)
            and self.allowed_assignment_types[0] == self.rate_card.car_type
            and all(isinstance(kind, CarType) for kind in self.allowed_assignment_types)
            and len(set(self.allowed_assignment_types)) == len(self.allowed_assignment_types),
            "INVALID_UPGRADES",
            "Invalid captured assignment types.",
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
    surge_adjustment: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        for field in (
            "distance_charge",
            "minimum_fare_adjustment",
            "surge_adjustment",
            "discount",
            "total",
        ):
            money(getattr(self, field), field)
        require(
            self.distance_charge
            + self.minimum_fare_adjustment
            + self.surge_adjustment
            - self.discount
            == self.total,
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
    cancellation: CancellationDetails | None = None

    def __post_init__(self) -> None:
        for field in ("id", "user_id", "driver_id"):
            clean_text(getattr(self, field), field)
        require(
            isinstance(self.requested_type, CarType) and isinstance(self.assigned_type, CarType),
            "INVALID_CAR_TYPE",
            "Unsupported car type.",
        )
        require(isinstance(self.pickup, Location), "INVALID_LOCATION", "Pickup is required.")
        require(
            isinstance(self.terms, BookingTerms), "INVALID_RATE_CARD", "Booking terms required."
        )
        require(
            self.assigned_type in self.terms.allowed_assignment_types,
            "INVALID_RIDE_STATE",
            "Assignment is not permitted by captured upgrade rules.",
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
        elif self.status == RideStatus.COMPLETED:
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

        if self.status == RideStatus.CANCELLED:
            require(
                all(item is None for item in completion)
                and isinstance(self.cancellation, CancellationDetails),
                "INVALID_RIDE_STATE",
                "Cancelled rides require only cancellation details.",
            )
            require(
                self.cancellation.cancelled_at >= self.started_at,
                "INVALID_RIDE_STATE",
                "Cancellation cannot precede booking.",
            )
        else:
            require(
                self.cancellation is None,
                "INVALID_RIDE_STATE",
                "Only cancelled rides can contain cancellation details.",
            )

    def cancel(self, details: CancellationDetails) -> Self:
        require(
            self.status == RideStatus.ONGOING,
            "INVALID_RIDE_STATE",
            "Only ongoing rides can be cancelled.",
        )
        return replace(self, status=RideStatus.CANCELLED, cancellation=details)

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

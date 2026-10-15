"""Core invariants also protect callers that do not use HTTP validation."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from ride_app.application.contracts import CompleteRideCommand, RegisterUserCommand
from ride_app.domain.errors import DomainError
from ride_app.domain.models import (
    BookingTerms,
    CarType,
    CouponTerms,
    DiscountType,
    FareBreakdown,
    Location,
    Ride,
    RideStatus,
)
from ride_app.infrastructure.configuration import ConfiguredRateCardCatalog


@pytest.mark.parametrize(("lat", "lng"), [(91, 0), (0, 181), (float("nan"), 0), (0, float("inf"))])
def test_invalid_coordinates_are_rejected(lat, lng):
    with pytest.raises(DomainError, match="must be finite"):
        Location(lat, lng)


@pytest.mark.parametrize("name", ["", "  ", None])
def test_invalid_names_are_rejected(name):
    with pytest.raises(DomainError):
        RegisterUserCommand(name)


@pytest.mark.parametrize("value", ["0", "-1", "101", "NaN", "Infinity"])
def test_invalid_coupon_percentages_are_rejected(value):
    with pytest.raises(DomainError):
        CouponTerms(DiscountType.PERCENTAGE, D(value))


def make_ride():
    return Ride(
        "R1",
        "U1",
        "D1",
        CarType.HATCHBACK,
        CarType.SEDAN,
        Location(0, 0),
        datetime(2026, 1, 1, tzinfo=UTC),
        BookingTerms(ConfiguredRateCardCatalog().get_for(CarType.HATCHBACK)),
    )


def test_ride_state_and_upgrade_invariants():
    ride = make_ride()
    assert ride.is_upgrade
    with pytest.raises(FrozenInstanceError):
        ride.status = RideStatus.COMPLETED
    with pytest.raises(DomainError):
        replace(ride, status=RideStatus.COMPLETED)
    with pytest.raises(DomainError):
        replace(ride, requested_type=CarType.SEDAN, assigned_type=CarType.HATCHBACK)
    with pytest.raises(DomainError):
        replace(ride, terms=BookingTerms(ConfiguredRateCardCatalog().get_for(CarType.SEDAN)))
    with pytest.raises(DomainError):
        replace(ride, started_at=datetime(2026, 1, 1))
    receipt = FareBreakdown(D("10"), D("40"), D("0"), D("50"))
    with pytest.raises(DomainError):
        ride.complete(D("1"), Location(0, 0), receipt, ride.started_at - timedelta(seconds=1))


def test_negative_completion_distance_rejected_before_service_call():
    with pytest.raises(DomainError):
        CompleteRideCommand("R1", D("-1"), Location(0, 0))


def test_receipt_must_reconcile_and_use_whole_paise():
    with pytest.raises(DomainError):
        FareBreakdown(D("10"), D("40"), D("5"), D("50"))
    with pytest.raises(DomainError):
        FareBreakdown(D(".001"), D("0"), D("0"), D(".001"))

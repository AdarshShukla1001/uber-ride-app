"""Test raw tier charges as well as totals: the minimum can mask tier errors."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from ride_app.domain.errors import DomainError
from ride_app.domain.models import (
    BookingTerms,
    CarType,
    CouponTerms,
    DiscountType,
    PricingTier,
    RateCard,
)
from ride_app.domain.pricing import PricingEngine, calculate_distance_charge
from ride_app.infrastructure.configuration import ConfiguredRateCardCatalog


@pytest.fixture
def hatchback():
    return ConfiguredRateCardCatalog().get_for(CarType.HATCHBACK)


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        ("0", "0.00"),
        ("1.999", "19.99"),
        ("2", "20.00"),
        ("2.001", "20.01"),
        ("2.5", "24.00"),
        ("4.999", "43.99"),
        ("5", "44.00"),
        ("5.001", "44.01"),
        ("6", "49.00"),
        ("10", "69.00"),
    ],
)
def test_raw_marginal_tiers(hatchback, distance, expected):
    assert calculate_distance_charge(D(distance), hatchback) == D(expected)


@pytest.mark.parametrize(
    ("car_type", "distance", "expected"),
    [
        (CarType.HATCHBACK, "0", "50.00"),
        (CarType.HATCHBACK, "5", "50.00"),
        (CarType.HATCHBACK, "6", "50.00"),
        (CarType.HATCHBACK, "10", "69.00"),
        (CarType.SEDAN, "1", "70.00"),
        (CarType.SEDAN, "10", "101.00"),
    ],
)
def test_minimum_and_car_type_rates(car_type, distance, expected):
    terms = BookingTerms(ConfiguredRateCardCatalog().get_for(car_type))
    receipt = PricingEngine().calculate(D(distance), terms)
    assert receipt.total == D(expected)
    assert receipt.total == receipt.distance_charge + receipt.minimum_fare_adjustment


@pytest.mark.parametrize(
    ("distance", "percentage", "discount", "total"),
    [
        ("10", "10", "6.90", "62.10"),
        ("1", "10", "5.00", "45.00"),
        ("10", "100", "69.00", "0.00"),
        ("1", "0.01", "0.01", "49.99"),
    ],
)
def test_coupon_after_minimum_and_half_up_rounding(
    hatchback, distance, percentage, discount, total
):
    terms = BookingTerms(hatchback, CouponTerms(DiscountType.PERCENTAGE, D(percentage)), "SAVE")
    receipt = PricingEngine().calculate(D(distance), terms)
    assert receipt.discount == D(discount)
    assert receipt.total == D(total)


def test_round_combined_tiers_once(hatchback):
    card = replace(hatchback, tiers=(PricingTier(D("1"), D(".005")), PricingTier(None, D(".005"))))
    assert calculate_distance_charge(D("2"), card) == D(".01")


@pytest.mark.parametrize("distance", ["-1", "NaN", "sNaN", "Infinity", "-Infinity", "1E10000"])
def test_invalid_distance_is_a_domain_error(hatchback, distance):
    with pytest.raises(DomainError) as error:
        PricingEngine().calculate(D(distance), BookingTerms(hatchback))
    assert error.value.code == "INVALID_DISTANCE"


def test_new_tier_is_a_configuration_change(hatchback):
    card = replace(
        hatchback,
        tiers=(
            PricingTier(D("2"), D("10")),
            PricingTier(D("5"), D("8")),
            PricingTier(D("10"), D("5")),
            PricingTier(None, D("3")),
        ),
    )
    assert calculate_distance_charge(D("12"), card) == D("75.00")


@pytest.mark.parametrize(
    "tiers",
    [
        (),
        (PricingTier(D("2"), D("10")),),
        (PricingTier(None, D("10")), PricingTier(None, D("5"))),
        (PricingTier(D("5"), D("10")), PricingTier(D("2"), D("8")), PricingTier(None, D("5"))),
    ],
)
def test_invalid_rate_schedule_is_rejected(tiers):
    with pytest.raises(DomainError):
        RateCard("bad", CarType.HATCHBACK, D("50"), tiers)

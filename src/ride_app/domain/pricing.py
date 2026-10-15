"""Pure pricing boundary; no persistence or transport dependencies."""

from decimal import Decimal

from ride_app.domain.errors import FeatureNotImplemented
from ride_app.domain.models import BookingTerms, CouponTerms, FareBreakdown, RateCard


def calculate_distance_charge(distance_km: Decimal, rate_card: RateCard) -> Decimal:
    """Calculate marginal tier charges independently of the minimum fare."""
    # Keep raw tier charges testable: minimum fares can hide incorrect tier arithmetic.
    raise FeatureNotImplemented("Tiered distance pricing")


def calculate_discount(subtotal: Decimal, terms: CouponTerms | None) -> Decimal:
    """Calculate the rounded discount, capped at the subtotal."""
    raise FeatureNotImplemented("Coupon discount calculation")


class PricingEngine:
    """Apply captured rates, the pre-discount minimum, and captured coupon terms."""

    def calculate(self, distance_km: Decimal, terms: BookingTerms) -> FareBreakdown:
        """Return an itemized receipt without reading repositories or mutating a ride."""
        # Planned order: rounded distance charge, minimum adjustment, then rounded discount.
        # Billing consumes captured terms, so later configuration changes cannot affect it.
        raise FeatureNotImplemented("Fare calculation")

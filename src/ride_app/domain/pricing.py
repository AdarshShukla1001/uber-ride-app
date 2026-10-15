"""Pure fare calculation: marginal tiers, minimum, captured surge, then coupon."""

from decimal import ROUND_HALF_UP, Decimal, DecimalException

from ride_app.domain.errors import DomainError
from ride_app.domain.models import BookingTerms, CouponTerms, DiscountType, FareBreakdown, RateCard
from ride_app.domain.validation import nonnegative_decimal

PAISE = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def calculate_distance_charge(distance_km: Decimal, rate_card: RateCard) -> Decimal:
    """Sum unrounded marginal segments, then round once; minimum fare is separate."""
    nonnegative_decimal(distance_km, "distance_km", "INVALID_DISTANCE")
    charge, lower = Decimal("0"), Decimal("0")
    try:
        for tier in rate_card.tiers:
            upper = distance_km if tier.upper_bound_km is None else tier.upper_bound_km
            segment = max(Decimal("0"), min(distance_km, upper) - lower)
            charge += segment * tier.rate_per_km
            if distance_km <= upper:
                break
            lower = upper
        return round_money(charge)
    except DecimalException as exc:
        raise DomainError(
            "INVALID_DISTANCE", "Distance exceeds supported decimal precision."
        ) from exc


def calculate_discount(subtotal: Decimal, terms: CouponTerms | None) -> Decimal:
    """Apply percentage or flat discount to the surged subtotal, capped at that subtotal."""
    nonnegative_decimal(subtotal, "subtotal")
    if terms is None:
        return Decimal("0.00")
    discount = (
        subtotal * terms.value / Decimal("100")
        if terms.discount_type == DiscountType.PERCENTAGE
        else terms.value
    )
    return min(subtotal, round_money(discount))


class PricingEngine:
    """Consume captured terms, with no database lookup or current-time dependency."""

    def calculate(self, distance_km: Decimal, terms: BookingTerms) -> FareBreakdown:
        try:
            distance_charge = calculate_distance_charge(distance_km, terms.rate_card)
            base = max(distance_charge, terms.rate_card.minimum_fare)
            subtotal = round_money(base * terms.surge_multiplier)
            discount = calculate_discount(subtotal, terms.coupon_terms)
            return FareBreakdown(
                distance_charge=distance_charge,
                minimum_fare_adjustment=round_money(base - distance_charge),
                surge_adjustment=round_money(subtotal - base),
                discount=round_money(discount),
                total=round_money(subtotal - discount),
            )
        except DecimalException as exc:
            raise DomainError(
                "INVALID_AMOUNT", "Fare exceeds supported decimal precision."
            ) from exc

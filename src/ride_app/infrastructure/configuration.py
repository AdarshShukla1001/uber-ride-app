"""Explicit exercise assumptions, kept separate from pricing algorithms."""

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from types import MappingProxyType

from ride_app.domain.models import CarType, PricingTier, RateCard


@dataclass(frozen=True, slots=True)
class Settings:
    """Application-wide matching configuration, independent of a customer's request."""

    search_radius_km: float = 5.0

    def __post_init__(self) -> None:
        if not isfinite(self.search_radius_km) or self.search_radius_km <= 0:
            raise ValueError("search_radius_km must be finite and positive")


class ConfiguredRateCardCatalog:
    """Exercise rate cards; Sedan rates are explicit assumptions recorded in the PRD."""

    def __init__(self) -> None:
        # Read-only mapping plus frozen records prevents changing captured rate terms.
        # Tier boundaries are cumulative: 0–2 km, above 2–5 km, then above 5 km.
        self._cards = MappingProxyType(
            {
                CarType.HATCHBACK: RateCard(
                    version="hatchback-v1",
                    car_type=CarType.HATCHBACK,
                    minimum_fare=Decimal("50.00"),
                    tiers=(
                        PricingTier(Decimal("2"), Decimal("10")),
                        PricingTier(Decimal("5"), Decimal("8")),
                        PricingTier(None, Decimal("5")),
                    ),
                ),
                CarType.SEDAN: RateCard(
                    version="sedan-v1",
                    car_type=CarType.SEDAN,
                    minimum_fare=Decimal("70.00"),
                    tiers=(
                        PricingTier(Decimal("2"), Decimal("14")),
                        PricingTier(Decimal("5"), Decimal("11")),
                        PricingTier(None, Decimal("8")),
                    ),
                ),
            }
        )

    def get_for(self, car_type: CarType) -> RateCard:
        return self._cards[car_type]

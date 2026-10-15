"""Explicit exercise assumptions, kept separate from pricing algorithms."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from math import isfinite
from pathlib import Path
from types import MappingProxyType

from ride_app.domain.models import CancellationTerms, CarType, PricingTier, RateCard, UpgradeRules
from ride_app.domain.policies import DemandSupplySurgePolicy


@dataclass(frozen=True, slots=True)
class Settings:
    """Application-wide matching configuration, independent of a customer's request."""

    search_radius_km: float = 5.0
    matching_strategy: str = "nearest"
    surge_policy: str = "none"
    surge_maximum: Decimal = Decimal("3")
    surge_sensitivity: Decimal = Decimal("0.5")
    cancellation_policy: str = "grace_period"
    cancellation_terms: CancellationTerms = field(default_factory=CancellationTerms)
    upgrades: UpgradeRules = field(default_factory=UpgradeRules)

    def __post_init__(self) -> None:
        if (
            type(self.search_radius_km) not in (int, float)
            or not isfinite(self.search_radius_km)
            or self.search_radius_km <= 0
        ):
            raise ValueError("search_radius_km must be finite and positive")
        if not isinstance(self.matching_strategy, str) or self.matching_strategy not in {
            "nearest",
            "highest_rated",
        }:
            raise ValueError("Unknown matching strategy")
        if not isinstance(self.surge_policy, str) or self.surge_policy not in {
            "none",
            "demand_supply",
        }:
            raise ValueError("Unknown surge policy")
        if not isinstance(self.cancellation_policy, str) or self.cancellation_policy not in {
            "free",
            "grace_period",
        }:
            raise ValueError("Unknown cancellation policy")
        if not isinstance(self.cancellation_terms, CancellationTerms) or not isinstance(
            self.upgrades, UpgradeRules
        ):
            raise ValueError("Invalid cancellation or upgrade configuration")
        DemandSupplySurgePolicy(self.surge_maximum, self.surge_sensitivity)


class ConfiguredRateCardCatalog:
    """Exercise rate cards; Sedan rates are explicit assumptions recorded in the PRD."""

    def __init__(self, cards: Mapping[CarType, RateCard] | None = None) -> None:
        # Read-only mapping plus frozen records prevents changing captured rate terms.
        # Tier boundaries are cumulative: 0–2 km, above 2–5 km, then above 5 km.
        defaults = {
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
            CarType.SUV: RateCard(
                version="suv-v1",
                car_type=CarType.SUV,
                minimum_fare=Decimal("100.00"),
                tiers=(
                    PricingTier(Decimal("2"), Decimal("20")),
                    PricingTier(Decimal("5"), Decimal("16")),
                    PricingTier(None, Decimal("12")),
                ),
            ),
        }
        if cards is not None:
            defaults.update(cards)
        for kind, card in defaults.items():
            if (
                not isinstance(kind, CarType)
                or not isinstance(card, RateCard)
                or card.car_type != kind
            ):
                raise ValueError("Rate card keys must match their car type")
        self._cards = MappingProxyType(defaults)

    def get_for(self, car_type: CarType) -> RateCard:
        return self._cards[car_type]


def _table(value: object, allowed: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"Invalid or unknown fields in {name}")
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Decimal configuration must be a number or decimal string")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("Invalid decimal configuration") from exc
    if not result.is_finite():
        raise ValueError("Configuration numbers must be finite")
    return result


def load_configuration(path: str | Path) -> tuple[Settings, ConfiguredRateCardCatalog]:
    """Load once at startup; no silent typos, arbitrary imports, or live repricing."""
    with Path(path).open("rb") as stream:
        raw = tomllib.load(stream, parse_float=Decimal)
    _table(raw, {"matching", "surge", "cancellation", "upgrades", "rates"}, "root")
    matching = _table(raw.get("matching", {}), {"radius_km", "strategy"}, "matching")
    surge = _table(raw.get("surge", {}), {"policy", "maximum", "sensitivity"}, "surge")
    cancellation = _table(
        raw.get("cancellation", {}), {"policy", "grace_seconds", "fee"}, "cancellation"
    )
    routes = dict(UpgradeRules().routes)
    for requested, targets in _table(raw.get("upgrades", {}), set(CarType), "upgrades").items():
        if not isinstance(targets, list):
            raise ValueError("Upgrade routes must be arrays")
        routes[CarType(requested)] = tuple(CarType(kind) for kind in targets)
    settings = Settings(
        search_radius_km=float(_decimal(matching.get("radius_km", 5))),
        matching_strategy=matching.get("strategy", "nearest"),
        surge_policy=surge.get("policy", "none"),
        surge_maximum=_decimal(surge.get("maximum", "3")),
        surge_sensitivity=_decimal(surge.get("sensitivity", "0.5")),
        cancellation_policy=cancellation.get("policy", "grace_period"),
        cancellation_terms=CancellationTerms(
            cancellation.get("grace_seconds", 120), _decimal(cancellation.get("fee", "20.00"))
        ),
        upgrades=UpgradeRules(tuple(routes.items())),
    )
    cards = {}
    for name, data in _table(raw.get("rates", {}), set(CarType), "rates").items():
        data = _table(data, {"version", "minimum_fare", "tiers"}, f"rates.{name}")
        if set(data) != {"version", "minimum_fare", "tiers"} or not isinstance(data["tiers"], list):
            raise ValueError("Each rate override needs version, minimum_fare and tiers")
        tiers = []
        for tier in data["tiers"]:
            tier = _table(tier, {"upper_bound_km", "rate_per_km"}, "tier")
            if "rate_per_km" not in tier:
                raise ValueError("Every tier needs rate_per_km")
            tiers.append(
                PricingTier(
                    _decimal(tier["upper_bound_km"]) if "upper_bound_km" in tier else None,
                    _decimal(tier["rate_per_km"]),
                )
            )
        kind = CarType(name)
        cards[kind] = RateCard(data["version"], kind, _decimal(data["minimum_fare"]), tuple(tiers))
    return settings, ConfiguredRateCardCatalog(cards)

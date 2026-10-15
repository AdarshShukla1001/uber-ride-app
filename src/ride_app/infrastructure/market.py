"""Exercise demand proxy; replace this adapter when real request telemetry exists."""

from ride_app.application.ports import DriverRepository, RideRepository
from ride_app.domain.matching import distance_km
from ride_app.domain.models import CarType, Location, UpgradeRules
from ride_app.domain.policies import MarketConditions


class LocalMarketConditionsProvider:
    """Ongoing same-type pickups + this request vs compatible available nearby cabs.

    Caller holds the application's shared mutation guard. Active rides are a
    disclosed demand proxy, not a queue of unfulfilled requests.
    """

    def __init__(
        self,
        rides: RideRepository,
        drivers: DriverRepository,
        radius_km: float,
        upgrades: UpgradeRules,
    ) -> None:
        self._rides = rides
        self._drivers = drivers
        self._radius = radius_km
        self._upgrades = upgrades

    def snapshot(self, pickup: Location, requested_type: CarType) -> MarketConditions:
        demand = 1 + sum(
            ride.requested_type == requested_type
            and distance_km(pickup, ride.pickup) <= self._radius
            for ride in self._rides.find_ongoing()
        )
        allowed = self._upgrades.types_for(requested_type)
        supply = sum(
            driver.cab.car_type in allowed
            and distance_km(pickup, driver.cab.location) <= self._radius
            for driver in self._drivers.find_available()
        )
        return MarketConditions(demand, supply)

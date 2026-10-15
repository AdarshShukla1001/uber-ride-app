from dataclasses import replace
from math import nextafter

import pytest

from ride_app.domain.errors import DomainError
from ride_app.domain.matching import DriverMatcher, NearestDriverStrategy, distance_km
from ride_app.domain.models import Cab, CarType, Driver, Location

PICKUP = Location(0, 0)


def driver(identifier, lng, car_type=CarType.HATCHBACK):
    return Driver(identifier, "Driver", Cab(identifier, car_type, Location(0, lng)))


def matcher():
    return DriverMatcher(NearestDriverStrategy())


def test_haversine_known_distance_and_antimeridian():
    assert distance_km(PICKUP, PICKUP) == 0
    assert distance_km(PICKUP, Location(0, 1)) == pytest.approx(111.19508)
    assert distance_km(Location(0, 179.9), Location(0, -179.9)) == pytest.approx(22.239, abs=0.001)
    assert distance_km(PICKUP, Location(0, 180)) == pytest.approx(20015.114, abs=0.001)


def test_nearest_and_stable_tie_breaker():
    candidates = [driver("B", 0.01), driver("C", 0.02), driver("A", 0.01)]
    assert matcher().match(candidates, PICKUP, CarType.HATCHBACK, 5).driver.id == "A"


def test_hatchback_before_nearer_sedan():
    candidates = [driver("S", 0, CarType.SEDAN), driver("H", 0.01)]
    assert matcher().match(candidates, PICKUP, CarType.HATCHBACK, 5).driver.id == "H"


def test_busy_and_out_of_radius_hatchbacks_allow_upgrade():
    candidates = [
        replace(driver("H1", 0), active_ride_id="R1"),
        driver("H2", 1),
        driver("S", 0.01, CarType.SEDAN),
    ]
    assert matcher().match(candidates, PICKUP, CarType.HATCHBACK, 5).driver.id == "S"


def test_radius_is_inclusive_without_admitting_outside_driver():
    candidate = driver("H", 0.01)
    radius = distance_km(PICKUP, candidate.cab.location)
    assert matcher().match([candidate], PICKUP, CarType.HATCHBACK, radius).driver == candidate
    with pytest.raises(DomainError) as error:
        matcher().match([candidate], PICKUP, CarType.HATCHBACK, nextafter(radius, 0))
    assert error.value.code == "NO_DRIVER_AVAILABLE"


@pytest.mark.parametrize("candidates", [[], [driver("H", 0)], [driver("S", 1, CarType.SEDAN)]])
def test_sedan_request_does_not_downgrade_or_ignore_radius(candidates):
    with pytest.raises(DomainError, match="No eligible driver"):
        matcher().match(candidates, PICKUP, CarType.SEDAN, 5)


def test_custom_ranking_still_receives_only_eligible_requested_type():
    class LastIdStrategy:
        def select(self, candidates, pickup):
            assert all(d.cab.car_type == CarType.HATCHBACK for d in candidates)
            return max(candidates, key=lambda d: d.id)

    candidates = [driver("H1", 0), driver("H2", 0.01), driver("S", 0, CarType.SEDAN)]
    result = DriverMatcher(LastIdStrategy()).match(candidates, PICKUP, CarType.HATCHBACK, 5)
    assert result.driver.id == "H2"

"""Behavioral coverage of policy selection, snapshots, lifecycle and config extensions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_cli import run_session
from test_matching import PICKUP, driver
from test_ride_workflows import HERE, book, finish, user
from test_ride_workflows import driver as register_driver

from ride_app.__main__ import main
from ride_app.application.contracts import (
    AddCouponCommand,
    BookRideCommand,
    CancelRideCommand,
    RegisterDriverCommand,
)
from ride_app.bootstrap import create_application
from ride_app.domain.errors import DomainError
from ride_app.domain.matching import (
    DriverMatcher,
    HighestRatedDriverStrategy,
    NearestDriverStrategy,
)
from ride_app.domain.models import (
    BookingTerms,
    CancellationTerms,
    CarType,
    CouponTerms,
    DiscountType,
    RideStatus,
    UpgradeRules,
)
from ride_app.domain.policies import DemandSupplySurgePolicy, MarketConditions, NoSurgePolicy
from ride_app.domain.pricing import PricingEngine
from ride_app.infrastructure.configuration import (
    ConfiguredRateCardCatalog,
    Settings,
    load_configuration,
)
from ride_app.interfaces.api import create_api


def test_highest_rating_then_distance_then_id_and_unrated_last():
    candidates = [
        replace(driver("unrated", 0), rating=None),
        replace(driver("low", 0), rating=D("4")),
        replace(driver("far", 0.02), rating=D("5")),
        replace(driver("B", 0.01), rating=D("5")),
        replace(driver("A", 0.01), rating=D("5")),
        replace(driver("busy", 0), rating=D("5"), active_ride_id="R"),
        replace(driver("outside", 1), rating=D("5")),
        replace(driver("sedan", 0, CarType.SEDAN), rating=D("5")),
    ]
    matcher = DriverMatcher(HighestRatedDriverStrategy())
    assert matcher.match(candidates, PICKUP, CarType.HATCHBACK, 5).driver.id == "A"
    assert (
        matcher.match(
            [candidates[0], replace(candidates[1], rating=D("0"))], PICKUP, CarType.HATCHBACK, 5
        ).driver.id
        == "low"
    )


def test_strategy_switch_in_bootstrap_changes_assignment():
    for strategy, expected in [("nearest", "near"), ("highest_rated", "rated")]:
        app = create_application(Settings(matching_strategy=strategy))
        rider = user(app)
        drivers = {}
        for registration, rating, lng in [("near", "3", 0), ("rated", "5", 0.01)]:
            drivers[registration] = app.registration.register_driver(
                RegisterDriverCommand(
                    registration, registration, CarType.HATCHBACK, type(HERE)(0, lng), D(rating)
                )
            )
        assert book(app, rider.id).driver_id == drivers[expected].id


@pytest.mark.parametrize("rating", ["-1", "5.01", "NaN", "Infinity"])
def test_invalid_rating_rejected_in_core(rating):
    with pytest.raises(DomainError):
        RegisterDriverCommand("D", "CAB", CarType.HATCHBACK, HERE, D(rating))


@pytest.mark.parametrize(
    ("demand", "supply", "expected"),
    [
        (0, 0, "1"),
        (1, 0, "1"),
        (1, 2, "1"),
        (2, 1, "1.5"),
        (100, 1, "3"),
    ],
)
def test_demand_supply_formula_and_caps(demand, supply, expected):
    market = MarketConditions(demand, supply)
    assert DemandSupplySurgePolicy().multiplier(market) == D(expected)
    assert NoSurgePolicy().multiplier(market) == 1


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        (DiscountType.PERCENTAGE, "10", "93.15"),
        (DiscountType.FLAT, "20", "83.50"),
        (DiscountType.FLAT, "200", "0.00"),
    ],
)
def test_surge_then_coupon_and_receipt_reconciliation(kind, value, expected):
    terms = BookingTerms(
        ConfiguredRateCardCatalog().get_for(CarType.HATCHBACK),
        CouponTerms(kind, D(value)),
        "SAVE",
        surge_multiplier=D("1.5"),
    )
    receipt = PricingEngine().calculate(D("10"), terms)
    assert receipt.distance_charge == D("69")
    assert receipt.surge_adjustment == D("34.50")
    assert receipt.total == D(expected)
    assert (
        receipt.distance_charge
        + receipt.minimum_fare_adjustment
        + receipt.surge_adjustment
        - receipt.discount
        == receipt.total
    )
    minimum = PricingEngine().calculate(D("0"), replace(terms, coupon_terms=None, coupon_code=None))
    assert minimum.minimum_fare_adjustment == D("50")
    assert minimum.surge_adjustment == D("25")
    assert minimum.total == D("75")


def test_real_local_market_surges_second_booking_and_preserves_snapshot():
    app = create_application(Settings(surge_policy="demand_supply"))
    register_driver(app, "CAB1")
    register_driver(app, "CAB2")
    first, second = user(app), user(app)
    ride1 = book(app, first.id)
    ride2 = book(app, second.id)
    assert ride1.terms.surge_multiplier == 1
    assert ride2.terms.surge_multiplier == D("1.5")
    finish(app, ride1.id)  # Supply recovers; existing quote must not change.
    assert finish(app, ride2.id).receipt.total == D("103.50")
    assert book(app, first.id).terms.surge_multiplier == 1


def test_market_is_local_and_requested_type_specific():
    app = create_application(Settings(surge_policy="demand_supply"))
    register_driver(app, "FAR", location=type(HERE)(1, 1))
    rider = user(app)
    app.rides.book_ride(BookRideCommand(rider.id, type(HERE)(1, 1), CarType.HATCHBACK))
    register_driver(app, "SEDAN", CarType.SEDAN)
    book(app, user(app).id, CarType.SEDAN)
    register_driver(app, "LOCAL")
    assert book(app, user(app).id).terms.surge_multiplier == 1


def test_injected_market_and_surge_keep_upgrade_billing_and_fail_without_mutation():
    class Market:
        def snapshot(self, pickup, requested_type):
            return MarketConditions(3, 1)

    class Surge:
        value = D("2")

        def multiplier(self, market):
            assert market.demand == 3
            return self.value

    surge = Surge()
    app = create_application(surge_policy=surge, market=Market())
    cab = register_driver(app, car_type=CarType.SEDAN)
    rider = user(app)
    ride = book(app, rider.id)
    surge.value = D("0")
    assert finish(app, ride.id).receipt.total == D("138")
    with pytest.raises(DomainError, match="below one"):
        book(app, rider.id)
    assert app.registration.update_driver_location(cab.id, HERE).is_available
    assert len(app.rides.get_user_history(rider.id)) == 1


def test_flat_coupon_deletion_preserves_snapshot(app):
    register_driver(app)
    rider = user(app)
    app.coupons.add_coupon(AddCouponCommand("FLAT", CouponTerms(DiscountType.FLAT, D("20"))))
    ride = book(app, rider.id, coupon="FLAT")
    app.coupons.delete_coupon("FLAT")
    assert finish(app, ride.id).receipt.total == D("49")


@pytest.mark.parametrize("value", ["0", "-1", "0.001", "NaN", "Infinity"])
def test_invalid_flat_coupon(value):
    with pytest.raises(DomainError):
        CouponTerms(DiscountType.FLAT, D(value))


@pytest.mark.parametrize(("elapsed", "expected"), [(0, "0"), (120, "0"), (121, "20")])
def test_cancellation_grace_boundary_and_history(elapsed, expected):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    app = create_application(clock=lambda: now)
    cab, rider = register_driver(app), user(app)
    ride = book(app, rider.id)
    now += timedelta(seconds=elapsed)
    cancelled = app.rides.cancel_ride(CancelRideCommand(ride.id, "Plans changed"))
    assert cancelled.status == RideStatus.CANCELLED
    assert cancelled.cancellation.fee == D(expected)
    assert cancelled.receipt is None and cancelled.completed_at is None
    assert app.rides.get_user_history(rider.id) == (cancelled,)
    assert app.rides.get_driver_history(cab.id) == (cancelled,)
    assert book(app, rider.id).driver_id == cab.id
    # Repeating the old cancellation must not release a new ride or replace its reason.
    assert app.rides.cancel_ride(CancelRideCommand(ride.id, "Retry")) == cancelled
    assert not app.registration.update_driver_location(cab.id, HERE).is_available
    with pytest.raises(DomainError, match="cannot be completed"):
        finish(app, ride.id)


def test_completed_ride_cannot_cancel_and_cancelled_ride_model_invariants(app):
    register_driver(app)
    ride = finish(app, book(app, user(app).id).id)
    with pytest.raises(DomainError, match="cannot be cancelled"):
        app.rides.cancel_ride(CancelRideCommand(ride.id))
    with pytest.raises(DomainError):
        replace(ride, status=RideStatus.CANCELLED)
    with pytest.raises(DomainError):
        app.rides.cancel_ride(CancelRideCommand("missing"))


def test_cancellation_policy_injection_and_failure_preserve_state():
    class Fee:
        value = D("-1")

        def calculate(self, ride, cancelled_at):
            return self.value

    policy = Fee()
    app = create_application(cancellation_policy=policy)
    cab, rider = register_driver(app), user(app)
    ride = book(app, rider.id)
    with pytest.raises(DomainError):
        app.rides.cancel_ride(CancelRideCommand(ride.id))
    assert app.rides.get_ride(ride.id) == ride
    assert not app.registration.update_driver_location(cab.id, HERE).is_available
    policy.value = D("7.50")
    cancelled = app.rides.cancel_ride(CancelRideCommand(ride.id))
    assert cancelled.cancellation.fee == D("7.50")
    assert app.registration.update_driver_location(cab.id, HERE).is_available


def test_free_cancellation_and_invalid_clock():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    app = create_application(Settings(cancellation_policy="free"), clock=lambda: now)
    cab = register_driver(app)
    ride = book(app, user(app).id)
    assert ride.terms.cancellation_terms.fee == 0
    now -= timedelta(seconds=1)
    with pytest.raises(DomainError):
        app.rides.cancel_ride(CancelRideCommand(ride.id))
    assert not app.registration.update_driver_location(cab.id, HERE).is_available
    now += timedelta(days=1)
    assert app.rides.cancel_ride(CancelRideCommand(ride.id)).cancellation.fee == 0


def test_cancel_and_complete_race_has_exactly_one_terminal_outcome(app):
    register_driver(app)
    rider = user(app)
    ride = book(app, rider.id)
    barrier = Barrier(2)

    def attempt(cancel):
        barrier.wait(timeout=5)
        try:
            return (
                app.rides.cancel_ride(CancelRideCommand(ride.id))
                if cancel
                else finish(app, ride.id)
            )
        except DomainError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [True, False]))
    assert sum(isinstance(outcome, DomainError) for outcome in outcomes) == 1
    terminal = app.rides.get_ride(ride.id)
    assert terminal in outcomes
    assert terminal.status in {RideStatus.COMPLETED, RideStatus.CANCELLED}
    assert book(app, rider.id).driver_id == ride.driver_id


def test_two_cancellations_are_idempotent(app):
    register_driver(app)
    ride = book(app, user(app).id)
    barrier = Barrier(2)

    def cancel(_):
        barrier.wait(timeout=5)
        return app.rides.cancel_ride(CancelRideCommand(ride.id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cancel, range(2)))
    assert results[0] == results[1]


def test_suv_is_explicit_and_upgrades_follow_config_and_snapshot():
    routes = dict(UpgradeRules().routes)
    routes[CarType.HATCHBACK] = (CarType.HATCHBACK, CarType.SEDAN, CarType.SUV)
    app = create_application(Settings(upgrades=UpgradeRules(tuple(routes.items()))))
    register_driver(app, car_type=CarType.SUV)
    rider = user(app)
    ride = book(app, rider.id)
    assert ride.assigned_type == CarType.SUV
    assert ride.terms.allowed_assignment_types[-1] == CarType.SUV
    assert finish(app, ride.id).receipt.total == D("69")
    assert finish(app, book(app, rider.id, CarType.SUV).id).receipt.total == D("148")
    with pytest.raises(DomainError, match="No eligible driver"):
        DriverMatcher(NearestDriverStrategy()).match(
            [driver("SUV", 0, CarType.SUV)], PICKUP, CarType.HATCHBACK, 5
        )


def test_example_configuration_loads_and_new_tier_is_used():
    settings, cards = load_configuration("config/example.toml")
    assert settings.matching_strategy == "highest_rated"
    assert settings.surge_policy == "demand_supply"
    assert settings.upgrades.types_for(CarType.HATCHBACK)[-1] == CarType.SUV
    app = create_application(settings, rate_cards=cards)
    register_driver(app)
    assert finish(app, book(app, user(app).id).id, "12").receipt.total == D("75")


@pytest.mark.parametrize(
    "config",
    [
        "typo = 1",
        '[matching]\nstrategy="invalid"',
        "[matching]\nstrategy=[]",
        "[matching]\nradius_km=0",
        "[matching]\nradius_km=true",
        '[surge]\nmaximum="0.5"',
        '[surge]\nsensitivity="NaN"',
        "[cancellation]\ngrace_seconds=-1",
        '[cancellation]\nfee="0.001"',
        '[upgrades]\nhatchback=["sedan"]',
        '[upgrades]\nhatchback=["hatchback", "hatchback"]',
        '[rates.hatchback]\nversion="v2"',
        '[rates.hatchback]\nversion="v2"\nminimum_fare="50"\n'
        'tiers=[{rate_per_km="5", upper_bound_km="2"}]',
    ],
)
def test_invalid_configuration_fails_at_startup(tmp_path, config):
    path = tmp_path / "invalid.toml"
    path.write_text(config)
    with pytest.raises((ValueError, DomainError)):
        load_configuration(path)


def test_configured_cli_and_bad_configuration_exit(tmp_path, monkeypatch, capsys):
    lines = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    assert main(["cli", "--config", "config/example.toml"]) == 0
    assert main(["cli", "--config", str(tmp_path / "missing.toml")]) == 2
    assert "CONFIGURATION_ERROR" in capsys.readouterr().err


def test_cli_exposes_rating_flat_coupon_and_cancellation(app, monkeypatch, capsys):
    assert (
        run_session(
            app,
            monkeypatch,
            [
                "user register --name Alice",
                "driver register --name Bob --registration-number CAB "
                "--type suv --rating 4.8 --lat 0 --lng 0",
                "coupon add --code FLAT --flat 20",
                "ride book --user id-001 --type suv --lat 0 --lng 0 --coupon FLAT",
                'ride cancel --ride id-003 --reason "Plans changed"',
                "exit",
            ],
        )
        == 0
    )
    output = capsys.readouterr()
    assert not output.err
    assert '"status": "cancelled"' in output.out
    assert '"discount_type": "flat"' in output.out
    assert '"rating": "4.8"' in output.out


def test_api_bonus_lifecycle_and_contracts():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    app = create_application(
        Settings(surge_policy="demand_supply", matching_strategy="highest_rated"), clock=lambda: now
    )
    location = {"latitude": 0, "longitude": 0}
    with TestClient(create_api(app)) as client:
        users = [client.post("/users", json={"name": "Alice"}).json()["id"] for _ in range(2)]
        drivers = [
            client.post(
                "/drivers",
                json={
                    "name": "Bob",
                    "registration_number": str(i),
                    "car_type": "sedan",
                    "rating": rating,
                    "location": location,
                },
            ).json()
            for i, rating in enumerate(["4", "5"])
        ]
        coupon = client.post(
            "/coupons", json={"code": "FLAT", "discount_type": "flat", "value": "20"}
        )
        assert coupon.status_code == 201
        rides = [
            client.post(
                "/rides",
                json={
                    "user_id": uid,
                    "pickup": location,
                    "requested_type": "hatchback",
                    "coupon_code": "FLAT",
                },
            ).json()
            for uid in users
        ]
        assert rides[0]["driver_id"] == drivers[1]["id"]
        assert D(rides[1]["terms"]["surge_multiplier"]) == D("1.5")
        complete = client.post(
            f"/rides/{rides[1]['id']}/complete", json={"distance_km": "10", "dropoff": location}
        )
        assert complete.status_code == 200
        assert complete.json()["receipt"]["total"] == "83.50"
        now += timedelta(seconds=121)
        cancel = client.post(f"/rides/{rides[0]['id']}/cancel", json={"reason": "Changed plans"})
        assert cancel.status_code == 200
        assert cancel.json()["cancellation"]["fee"] == "20.00"  # Coupons don't discount fees.
        assert cancel.json()["receipt"] is None
        assert client.post(f"/rides/{rides[0]['id']}/cancel", json={}).json() == cancel.json()
        assert (
            client.post(
                f"/rides/{rides[0]['id']}/complete", json={"distance_km": "1", "dropoff": location}
            ).status_code
            == 409
        )
        assert client.post(f"/rides/{rides[1]['id']}/cancel", json={}).status_code == 409
        assert client.post("/rides/missing/cancel", json={}).status_code == 404
        for payload in [
            {"percentage": "10", "discount_type": "flat", "value": "2"},
            {"discount_type": "flat"},
            {"discount_type": "percentage", "value": "101"},
            {"discount_type": "flat", "value": "0.001"},
        ]:
            assert client.post("/coupons", json={"code": "BAD", **payload}).status_code == 422


def test_upgrade_rules_reject_mutable_nested_routes():
    routes = list(UpgradeRules().routes)
    routes[0] = list(routes[0])
    with pytest.raises(DomainError, match="immutable pair"):
        UpgradeRules(tuple(routes))


def test_cancellation_keeps_latest_location_and_captured_terms():
    observed = []

    class Capture:
        def select(self, candidates, pickup):
            observed.append(candidates[0].cab.location)
            return candidates[0]

    now = datetime(2026, 1, 1, tzinfo=UTC)
    settings = Settings(cancellation_terms=CancellationTerms(10, D("35")))
    app = create_application(settings, clock=lambda: now, matching_strategy=Capture())
    cab, rider = register_driver(app), user(app)
    ride = book(app, rider.id)
    latest = type(HERE)(0.01, 0)
    app.registration.update_driver_location(cab.id, latest)
    settings = replace(settings, cancellation_terms=CancellationTerms(0, D("999")))
    now += timedelta(seconds=11)
    cancelled = app.rides.cancel_ride(CancelRideCommand(ride.id))
    assert cancelled.cancellation.fee == D("35")
    assert cancelled.terms.cancellation_terms.fee != settings.cancellation_terms.fee
    book(app, rider.id)
    assert observed == [HERE, latest]

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D
from itertools import count
from threading import Barrier

import pytest

from ride_app.application.contracts import (
    AddCouponCommand,
    BookRideCommand,
    CompleteRideCommand,
    RegisterDriverCommand,
    RegisterUserCommand,
)
from ride_app.bootstrap import create_application
from ride_app.domain.errors import DomainError
from ride_app.domain.models import CarType, CouponTerms, DiscountType, Location, RideStatus
from ride_app.infrastructure.configuration import ConfiguredRateCardCatalog

HERE = Location(0, 0)


def user(app, name="Alice"):
    return app.registration.register_user(RegisterUserCommand(name))


def driver(app, registration="KA01", car_type=CarType.HATCHBACK, location=HERE):
    return app.registration.register_driver(
        RegisterDriverCommand("Bob", registration, car_type, location)
    )


def book(app, user_id, car_type=CarType.HATCHBACK, coupon=None):
    return app.rides.book_ride(BookRideCommand(user_id, HERE, car_type, coupon))


def finish(app, ride_id, distance="10", location=HERE):
    return app.rides.complete_ride(CompleteRideCommand(ride_id, D(distance), location))


def test_full_lifecycle_and_both_histories(app):
    rider, cab_driver = user(app), driver(app)
    assert app.rides.get_user_history(rider.id) == ()
    assert app.rides.get_driver_history(cab_driver.id) == ()
    ongoing = book(app, rider.id)
    assert ongoing.status == RideStatus.ONGOING
    assert ongoing.receipt is None
    assert app.rides.get_user_history(rider.id) == (ongoing,)
    completed = finish(app, ongoing.id)
    assert completed.receipt.total == D("69")
    assert completed.status == RideStatus.COMPLETED
    assert app.rides.get_ride(ongoing.id) == completed
    assert app.rides.get_user_history(rider.id) == (completed,)
    assert app.rides.get_driver_history(cab_driver.id) == (completed,)
    assert book(app, rider.id).driver_id == cab_driver.id


def test_duplicate_cab_normalization_and_trimmed_names(app):
    first = driver(app, registration=" ka01 ")
    assert first.cab.registration_number == "KA01"
    assert user(app, " Alice ").name == "Alice"
    with pytest.raises(DomainError) as error:
        driver(app, registration="KA01")
    assert error.value.code == "DUPLICATE_CAB"
    assert book(app, user(app).id).driver_id == first.id


def test_busy_driver_and_active_user_rejected(app):
    rider, other = user(app), user(app)
    driver(app)
    first = book(app, rider.id)
    with pytest.raises(DomainError) as error:
        book(app, rider.id)
    assert error.value.code == "USER_ALREADY_ON_RIDE"
    with pytest.raises(DomainError) as error:
        book(app, other.id)
    assert error.value.code == "NO_DRIVER_AVAILABLE"
    assert app.rides.get_user_history(other.id) == ()
    assert app.rides.get_ride(first.id).status == RideStatus.ONGOING


def test_free_upgrade_uses_requested_rates(app):
    rider = user(app)
    driver(app, car_type=CarType.SEDAN)
    ride = book(app, rider.id)
    assert ride.is_upgrade
    assert ride.assigned_type == CarType.SEDAN
    assert ride.terms.rate_card.car_type == CarType.HATCHBACK
    assert finish(app, ride.id).receipt.total == D("69")


def test_invalid_coupon_does_not_reserve_driver_or_create_ride(app):
    rider, available = user(app), driver(app)
    with pytest.raises(DomainError) as error:
        book(app, rider.id, coupon="MISSING")
    assert error.value.code == "INVALID_COUPON"
    assert app.rides.get_user_history(rider.id) == ()
    assert app.rides.get_driver_history(available.id) == ()
    assert book(app, rider.id).driver_id == available.id


def test_deleted_coupon_keeps_captured_terms_and_cannot_be_reused(app):
    rider = user(app)
    driver(app)
    app.coupons.add_coupon(
        AddCouponCommand(" save10 ", CouponTerms(DiscountType.PERCENTAGE, D("10")))
    )
    ride = book(app, rider.id, coupon="save10")
    assert ride.terms.coupon_code == "SAVE10"
    app.coupons.delete_coupon(" save10 ")
    app.coupons.delete_coupon("SAVE10")
    assert finish(app, ride.id).receipt.total == D("62.10")
    with pytest.raises(DomainError) as error:
        book(app, rider.id, coupon="SAVE10")
    assert error.value.code == "INVALID_COUPON"
    with pytest.raises(DomainError) as error:
        app.coupons.add_coupon(
            AddCouponCommand("SAVE10", CouponTerms(DiscountType.PERCENTAGE, D("20")))
        )
    assert error.value.code == "DUPLICATE_COUPON"


def test_rate_change_after_booking_does_not_reprice_ride():
    class MutableCatalog:
        card = ConfiguredRateCardCatalog().get_for(CarType.HATCHBACK)

        def get_for(self, car_type):
            return self.card

    catalog = MutableCatalog()
    app = create_application(rate_cards=catalog)
    rider = user(app)
    driver(app)
    ride = book(app, rider.id)
    catalog.card = replace(catalog.card, version="v2", minimum_fare=D("500"))
    assert finish(app, ride.id).receipt.total == D("69")
    assert finish(app, book(app, rider.id).id).receipt.total == D("500")


def test_repeat_completion_does_not_release_or_move_new_assignment(app):
    rider, other = user(app), user(app)
    cab_driver = driver(app)
    old = finish(app, book(app, rider.id).id)
    new = book(app, other.id)
    repeated = finish(app, old.id, distance="999", location=Location(1, 1))
    assert repeated == old
    with pytest.raises(DomainError) as error:
        book(app, rider.id)
    assert error.value.code == "NO_DRIVER_AVAILABLE"
    assert finish(app, new.id).driver_id == cab_driver.id
    assert book(app, rider.id).driver_id == cab_driver.id


def test_location_updates_affect_matching_and_completion_moves_cab(app):
    rider, cab_driver = user(app), driver(app)
    app.registration.update_driver_location(cab_driver.id, Location(1, 1))
    with pytest.raises(DomainError, match="within radius"):
        book(app, rider.id)
    app.registration.update_driver_location(cab_driver.id, HERE)
    ride = book(app, rider.id)
    # Intermediate GPS updates do not replace supplied billed distance.
    app.registration.update_driver_location(cab_driver.id, Location(0.01, 0))
    assert finish(app, ride.id, location=Location(1, 1)).receipt.total == D("69")
    with pytest.raises(DomainError, match="within radius"):
        book(app, rider.id)


def test_invalid_completion_leaves_ride_and_assignment_unchanged(app):
    rider = user(app)
    driver(app)
    ride = book(app, rider.id)
    with pytest.raises(DomainError):
        finish(app, ride.id, distance="-1")
    assert app.rides.get_ride(ride.id) == ride
    with pytest.raises(DomainError, match="No eligible driver"):
        book(app, user(app).id)
    assert finish(app, ride.id).receipt.total == D("69")


def test_pricing_failure_leaves_ongoing_ride_recoverable(app):
    rider = user(app)
    driver(app)
    ride = book(app, rider.id)
    # An enormous distance exercises a real pricing failure before any state writes.
    with pytest.raises(DomainError):
        finish(app, ride.id, distance="1E10000")
    assert app.rides.get_ride(ride.id) == ride
    assert finish(app, ride.id).receipt.total == D("69")


def test_booking_failure_before_commit_does_not_consume_driver():
    def broken_clock():
        raise RuntimeError("Clock unavailable")

    ids = count()
    app = create_application(new_id=lambda: str(next(ids)), clock=broken_clock)
    rider, cab_driver = user(app), driver(app)
    with pytest.raises(RuntimeError, match="Clock unavailable"):
        book(app, rider.id)
    assert app.rides.get_driver_history(cab_driver.id) == ()
    assert app.rides.get_user_history(rider.id) == ()
    # A location update returns the same still-unassigned driver.
    assert app.registration.update_driver_location(cab_driver.id, HERE).is_available


def test_histories_newest_first_then_stable_id():
    times = iter([datetime(2026, 1, day, tzinfo=UTC) for day in (1, 1, 2, 2, 2)])
    ids = count()
    app = create_application(new_id=lambda: str(next(ids)), clock=lambda: next(times))
    rider, cab_driver = user(app), driver(app)
    first = finish(app, book(app, rider.id).id)
    second = finish(app, book(app, rider.id).id)
    third = book(app, user(app).id)
    history = app.rides.get_driver_history(cab_driver.id)
    assert history == (second, third, first)


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        (lambda app: app.rides.get_ride("missing"), "RIDE_NOT_FOUND"),
        (lambda app: app.rides.get_user_history("missing"), "USER_NOT_FOUND"),
        (lambda app: app.rides.get_driver_history("missing"), "DRIVER_NOT_FOUND"),
        (lambda app: app.registration.update_driver_location("missing", HERE), "DRIVER_NOT_FOUND"),
        (lambda app: app.coupons.delete_coupon("missing"), "COUPON_NOT_FOUND"),
        (lambda app: book(app, "missing"), "USER_NOT_FOUND"),
        (lambda app: finish(app, "missing"), "RIDE_NOT_FOUND"),
    ],
)
def test_unknown_entities_report_stable_errors(app, operation, code):
    with pytest.raises(DomainError) as error:
        operation(app)
    assert error.value.code == code


def test_simultaneous_bookings_assign_one_driver_once(app):
    riders = [user(app), user(app)]
    available = driver(app)
    barrier = Barrier(2)

    def attempt(rider):
        barrier.wait(timeout=5)
        try:
            return book(app, rider.id)
        except DomainError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, riders))
    successes = [r for r in results if not isinstance(r, DomainError)]
    failures = [r for r in results if isinstance(r, DomainError)]
    assert len(successes) == len(failures) == 1
    assert successes[0].driver_id == available.id
    assert failures[0].code == "NO_DRIVER_AVAILABLE"
    assert app.rides.get_driver_history(available.id) == (successes[0],)

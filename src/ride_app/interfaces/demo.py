"""Deterministic acceptance walkthrough using the public application services."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count

from ride_app.application.contracts import (
    AddCouponCommand,
    BookRideCommand,
    CompleteRideCommand,
    RegisterDriverCommand,
    RegisterUserCommand,
)
from ride_app.bootstrap import create_application
from ride_app.domain.errors import DomainError
from ride_app.domain.models import CarType, CouponTerms, DiscountType, Location
from ride_app.interfaces.cli import to_json_value


def run_demo() -> int:
    identifiers = count(1)
    app = create_application(
        new_id=lambda: f"demo-{next(identifiers):02}",
        clock=lambda: datetime(2026, 10, 15, 12, tzinfo=UTC),
    )
    pickup = Location(12.97, 77.59)
    alice = app.registration.register_user(RegisterUserCommand("Alice"))
    priya = app.registration.register_user(RegisterUserCommand("Priya"))
    sedan = app.registration.register_driver(
        RegisterDriverCommand(
            "Sam",
            "KA01SEDAN",
            CarType.SEDAN,
            pickup,
        )
    )
    app.registration.register_driver(
        RegisterDriverCommand(
            "Hari",
            "KA01HATCH",
            CarType.HATCHBACK,
            pickup,
        )
    )

    def show(label: str, value: object) -> None:
        print(f"\n{label}\n{json.dumps(to_json_value(value), indent=2)}")

    normal = app.rides.book_ride(BookRideCommand(alice.id, pickup, CarType.HATCHBACK))
    minimum = app.rides.complete_ride(CompleteRideCommand(normal.id, Decimal("1"), pickup))
    show("1. Minimum-fare ride: INR 50.00", minimum)

    # Occupy the Hatchback, forcing the next Hatchback request to upgrade to Sedan.
    occupied = app.rides.book_ride(BookRideCommand(alice.id, pickup, CarType.HATCHBACK))
    app.coupons.add_coupon(
        AddCouponCommand(
            "SAVE10",
            CouponTerms(
                DiscountType.PERCENTAGE,
                Decimal("10"),
            ),
        )
    )
    upgraded = app.rides.book_ride(BookRideCommand(priya.id, pickup, CarType.HATCHBACK, "SAVE10"))
    if not upgraded.is_upgrade:
        raise RuntimeError("Demo expected a free upgrade.")
    app.coupons.delete_coupon("SAVE10")
    completed = app.rides.complete_ride(CompleteRideCommand(upgraded.id, Decimal("10"), pickup))
    show("2. Free Sedan upgrade, captured coupon after deletion: INR 62.10", completed)
    app.rides.complete_ride(CompleteRideCommand(occupied.id, Decimal("10"), pickup))
    show("3. User history", app.rides.get_user_history(priya.id))
    show("4. Driver history", app.rides.get_driver_history(sedan.id))

    for label, request, expected_code in (
        (
            "5. No driver within radius",
            BookRideCommand(alice.id, Location(0, 0), CarType.HATCHBACK),
            "NO_DRIVER_AVAILABLE",
        ),
        (
            "6. Deleted coupon cannot be applied again",
            BookRideCommand(alice.id, pickup, CarType.HATCHBACK, "SAVE10"),
            "INVALID_COUPON",
        ),
    ):
        try:
            app.rides.book_ride(request)
        except DomainError as exc:
            if exc.code != expected_code:
                raise
            show(label, {"error": {"code": exc.code, "message": exc.message}})
        else:
            raise RuntimeError(f"Demo expected {expected_code}.")
    print("\nDemo completed successfully.")
    return 0

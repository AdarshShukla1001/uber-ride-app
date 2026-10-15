"""Interactive CLI: retain one application context across commands."""

import argparse
import shlex
import sys
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pprint import pprint

from ride_app.application.contracts import (
    AddCouponCommand,
    BookRideCommand,
    CompleteRideCommand,
    RegisterDriverCommand,
    RegisterUserCommand,
)
from ride_app.bootstrap import Application
from ride_app.domain.errors import DomainError, FeatureNotImplemented
from ride_app.domain.models import CarType, CouponTerms, DiscountType, Location


def decimal_argument(value: str) -> Decimal:
    """Parse exact numeric text; business constraints such as sign belong in the core."""
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("Expected a finite decimal number.") from exc
    if not result.is_finite():
        raise argparse.ArgumentTypeError("Expected a finite decimal number.")
    return result


def add_location_arguments(parser: argparse.ArgumentParser) -> None:
    """Use consistent coordinate flags across registration, updates, and rides."""
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)


def build_command_parser() -> argparse.ArgumentParser:
    """Describe resource/action syntax without invoking services or creating state."""
    parser = argparse.ArgumentParser(prog="ride")
    resources = parser.add_subparsers(dest="resource", required=True)

    user = resources.add_parser("user").add_subparsers(dest="action", required=True)
    user_register = user.add_parser("register")
    user_register.add_argument("--name", required=True)
    user.add_parser("rides").add_argument("--user", required=True)

    driver = resources.add_parser("driver").add_subparsers(dest="action", required=True)
    driver_register = driver.add_parser("register")
    driver_register.add_argument("--name", required=True)
    driver_register.add_argument("--registration-number", required=True)
    driver_register.add_argument("--type", choices=list(CarType), required=True)
    add_location_arguments(driver_register)
    driver_location = driver.add_parser("location")
    driver_location.add_argument("--driver", required=True)
    add_location_arguments(driver_location)
    driver.add_parser("rides").add_argument("--driver", required=True)

    rides = resources.add_parser("ride").add_subparsers(dest="action", required=True)
    book = rides.add_parser("book")
    book.add_argument("--user", required=True)
    book.add_argument("--type", choices=list(CarType), required=True)
    book.add_argument("--coupon")
    add_location_arguments(book)
    end = rides.add_parser("end")
    end.add_argument("--ride", required=True)
    end.add_argument("--distance-km", type=decimal_argument, required=True)
    add_location_arguments(end)
    rides.add_parser("show").add_argument("--ride", required=True)

    coupons = resources.add_parser("coupon").add_subparsers(dest="action", required=True)
    add_coupon = coupons.add_parser("add")
    add_coupon.add_argument("--code", required=True)
    add_coupon.add_argument("--percentage", type=decimal_argument, required=True)
    coupons.add_parser("delete").add_argument("--code", required=True)
    return parser


def execute_command(application: Application, args: argparse.Namespace) -> object:
    """Translate parsed arguments into the same commands used by the API adapter."""
    match (args.resource, args.action):
        case ("user", "register"):
            return application.registration.register_user(RegisterUserCommand(name=args.name))
        case ("user", "rides"):
            return application.rides.get_user_history(args.user)
        case ("driver", "register"):
            return application.registration.register_driver(
                RegisterDriverCommand(
                    name=args.name,
                    registration_number=args.registration_number,
                    car_type=CarType(args.type),
                    location=Location(args.lat, args.lng),
                )
            )
        case ("driver", "location"):
            return application.registration.update_driver_location(
                args.driver,
                Location(args.lat, args.lng),
            )
        case ("driver", "rides"):
            return application.rides.get_driver_history(args.driver)
        case ("ride", "book"):
            return application.rides.book_ride(
                BookRideCommand(
                    user_id=args.user,
                    pickup=Location(args.lat, args.lng),
                    requested_type=CarType(args.type),
                    coupon_code=args.coupon,
                )
            )
        case ("ride", "end"):
            return application.rides.complete_ride(
                CompleteRideCommand(
                    ride_id=args.ride,
                    distance_km=args.distance_km,
                    dropoff=Location(args.lat, args.lng),
                )
            )
        case ("ride", "show"):
            return application.rides.get_ride(args.ride)
        case ("coupon", "add"):
            return application.coupons.add_coupon(
                AddCouponCommand(
                    code=args.code,
                    terms=CouponTerms(DiscountType.PERCENTAGE, args.percentage),
                )
            )
        case ("coupon", "delete"):
            application.coupons.delete_coupon(args.code)
            return None
        case _:
            raise ValueError("Unrecognized command")


def run_cli(application: Application) -> int:
    """Reuse one context until exit; remember failures for scripted stdin exit codes."""
    parser = build_command_parser()
    print("Ride CLI scaffold. Business operations are pending implementation.")
    print("Enter 'help', '<resource> --help', or 'exit'. State is local to this session.")
    failed = False
    while True:
        try:
            line = input("ride> ").strip()
        except EOFError:
            print()
            return int(failed)
        if line in {"exit", "quit"}:
            return int(failed)
        if not line:
            continue
        if line == "help":
            parser.print_help()
            continue
        try:
            args = parser.parse_args(shlex.split(line))
        except SystemExit as exc:
            # argparse exits for help and invalid syntax; neither should end the session.
            failed = failed or bool(exc.code)
            continue
        except ValueError as exc:
            print(f"INVALID_COMMAND: {exc}", file=sys.stderr)
            failed = True
            continue
        try:
            result = execute_command(application, args)
        except FeatureNotImplemented as exc:
            print(f"NOT_IMPLEMENTED: {exc}", file=sys.stderr)
            failed = True
        except DomainError as exc:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            failed = True
        else:
            if isinstance(result, tuple):
                pprint([asdict(item) for item in result])
            elif result is None:
                print("Done.")
            else:
                pprint(asdict(result))

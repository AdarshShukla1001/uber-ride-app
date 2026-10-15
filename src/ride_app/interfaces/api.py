"""HTTP adapter. Scaffolded use cases return an explicit 501 response."""

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ride_app.application.contracts import (
    AddCouponCommand,
    BookRideCommand,
    CompleteRideCommand,
    RegisterDriverCommand,
    RegisterUserCommand,
)
from ride_app.bootstrap import Application, create_application
from ride_app.domain.errors import DomainError, FeatureNotImplemented
from ride_app.domain.models import Coupon, CouponTerms, DiscountType, Driver, Ride, User
from ride_app.interfaces.schemas import (
    AddCouponRequest,
    BookRideRequest,
    CompleteRideRequest,
    LocationRequest,
    RegisterDriverRequest,
    RegisterUserRequest,
)


def create_api(application: Application | None = None) -> FastAPI:
    """Build routes around one application context for the server's lifetime.

    Supplying a context supports isolated adapter tests. No business rules belong
    in these handlers: each converts input and delegates to the shared service.
    """
    services = application if application is not None else create_application()
    api = FastAPI(
        title="Ride Hailing Backend",
        version="0.1.0",
        description=(
            "Project scaffold. Business endpoints currently return 501; "
            "domain workflows and output contracts are pending implementation."
        ),
    )

    @api.exception_handler(FeatureNotImplemented)
    async def feature_pending(request: Request, exc: FeatureNotImplemented) -> JSONResponse:
        """Expose scaffold status explicitly rather than report a successful operation."""
        return JSONResponse(
            status_code=501,
            content={"error": {"code": "NOT_IMPLEMENTED", "message": str(exc)}},
        )

    @api.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        """Translate transport-neutral failures into HTTP status and a stable envelope."""
        if exc.code.endswith("_NOT_FOUND"):
            status_code = 404
        elif exc.code in {
            "USER_ALREADY_ON_RIDE",
            "NO_DRIVER_AVAILABLE",
            "DUPLICATE_CAB",
            "DUPLICATE_COUPON",
            "DRIVER_ALREADY_ON_RIDE",
        }:
            status_code = 409
        else:
            status_code = 422
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Return field paths and messages without echoing the entire rejected payload.
        details = [
            {"field": ".".join(str(part) for part in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request validation failed.",
                    "details": details,
                }
            },
        )

    @api.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Report process responsiveness, not completion of business features."""
        return {"status": "ok", "implementation": "scaffold"}

    @api.post("/users", status_code=status.HTTP_201_CREATED, tags=["users"])
    def register_user(body: RegisterUserRequest) -> User:
        return services.registration.register_user(RegisterUserCommand(name=body.name))

    @api.post("/drivers", status_code=status.HTTP_201_CREATED, tags=["drivers"])
    def register_driver(body: RegisterDriverRequest) -> Driver:
        return services.registration.register_driver(
            RegisterDriverCommand(
                name=body.name,
                registration_number=body.registration_number,
                car_type=body.car_type,
                location=body.location.to_domain(),
            )
        )

    @api.patch("/drivers/{driver_id}/location", tags=["drivers"])
    def update_location(driver_id: str, body: LocationRequest) -> Driver:
        return services.registration.update_driver_location(driver_id, body.to_domain())

    @api.post("/rides", status_code=status.HTTP_201_CREATED, tags=["rides"])
    def book_ride(body: BookRideRequest) -> Ride:
        return services.rides.book_ride(
            BookRideCommand(
                user_id=body.user_id,
                pickup=body.pickup.to_domain(),
                requested_type=body.requested_type,
                coupon_code=body.coupon_code,
            )
        )

    @api.post("/rides/{ride_id}/complete", tags=["rides"])
    def complete_ride(ride_id: str, body: CompleteRideRequest) -> Ride:
        return services.rides.complete_ride(
            CompleteRideCommand(
                ride_id=ride_id,
                distance_km=body.distance_km,
                dropoff=body.dropoff.to_domain(),
            )
        )

    @api.get("/rides/{ride_id}", tags=["rides"])
    def get_ride(ride_id: str) -> Ride:
        return services.rides.get_ride(ride_id)

    @api.get("/users/{user_id}/rides", tags=["users"])
    def user_history(user_id: str) -> tuple[Ride, ...]:
        return services.rides.get_user_history(user_id)

    @api.get("/drivers/{driver_id}/rides", tags=["drivers"])
    def driver_history(driver_id: str) -> tuple[Ride, ...]:
        return services.rides.get_driver_history(driver_id)

    @api.post("/coupons", status_code=status.HTTP_201_CREATED, tags=["coupons"])
    def add_coupon(body: AddCouponRequest) -> Coupon:
        return services.coupons.add_coupon(
            AddCouponCommand(
                code=body.code,
                terms=CouponTerms(discount_type=DiscountType.PERCENTAGE, value=body.percentage),
            )
        )

    @api.delete("/coupons/{code}", status_code=status.HTTP_204_NO_CONTENT, tags=["coupons"])
    def delete_coupon(code: str) -> Response:
        services.coupons.delete_coupon(code)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return api

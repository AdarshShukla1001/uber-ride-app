"""Registration and cab-location use-case boundary."""

from ride_app.application.contracts import RegisterDriverCommand, RegisterUserCommand
from ride_app.application.ports import DriverRepository, IdGenerator, MutationGuard, UserRepository
from ride_app.domain.errors import FeatureNotImplemented
from ride_app.domain.models import Driver, Location, User


class RegistrationService:
    """Own registration validation and location updates for both transport adapters."""

    def __init__(
        self,
        users: UserRepository,
        drivers: DriverRepository,
        guard: MutationGuard,
        new_id: IdGenerator,
    ) -> None:
        self._users = users
        self._drivers = drivers
        self._guard = guard
        self._new_id = new_id

    def register_user(self, command: RegisterUserCommand) -> User:
        """Planned: validate the name, allocate an ID, and store a new rider."""
        raise FeatureNotImplemented("User registration")

    def register_driver(self, command: RegisterDriverCommand) -> Driver:
        """Planned: validate cab details and reject duplicate normalized registrations."""
        raise FeatureNotImplemented("Driver registration")

    def update_driver_location(self, driver_id: str, location: Location) -> Driver:
        """Planned: replace cab location under the same guard used by booking."""
        raise FeatureNotImplemented("Driver location update")

"""Registration and cab-location use-case boundary."""

from ride_app.application.contracts import RegisterDriverCommand, RegisterUserCommand
from ride_app.application.ports import DriverRepository, IdGenerator, MutationGuard, UserRepository
from ride_app.domain.models import Cab, Driver, Location, User
from ride_app.domain.validation import clean_text, require


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
        """Store a validated rider under the shared mutation boundary."""
        with self._guard.exclusive():
            user = User(self._new_id(), command.name)
            require(
                self._users.find_by_id(user.id) is None,
                "DUPLICATE_ID",
                "Generated user ID already exists.",
            )
            self._users.save(user)
            return user

    def register_driver(self, command: RegisterDriverCommand) -> Driver:
        """Reject duplicate normalized registrations before storing any record."""
        with self._guard.exclusive():
            require(
                self._drivers.find_by_registration(command.registration_number) is None,
                "DUPLICATE_CAB",
                "Cab registration already exists.",
            )
            driver = Driver(
                self._new_id(),
                command.name,
                Cab(
                    command.registration_number,
                    command.car_type,
                    command.location,
                ),
            )
            require(
                self._drivers.find_by_id(driver.id) is None,
                "DUPLICATE_ID",
                "Generated driver ID already exists.",
            )
            self._drivers.save(driver)
            return driver

    def update_driver_location(self, driver_id: str, location: Location) -> Driver:
        """Location changes and matching participate in the same synchronization boundary."""
        driver_id = clean_text(driver_id, "driver_id")
        with self._guard.exclusive():
            driver = self._drivers.find_by_id(driver_id)
            require(driver is not None, "DRIVER_NOT_FOUND", "Driver does not exist.")
            updated = driver.update_location(location)
            self._drivers.save(updated)
            return updated

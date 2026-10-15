"""Coupon creation and deactivation use-case boundary."""

from ride_app.application.contracts import AddCouponCommand
from ride_app.application.ports import CouponRepository, MutationGuard
from ride_app.domain.errors import FeatureNotImplemented
from ride_app.domain.models import Coupon


class CouponService:
    """Manage catalog availability without changing terms captured by existing rides."""

    def __init__(self, coupons: CouponRepository, guard: MutationGuard) -> None:
        self._coupons = coupons
        self._guard = guard

    def add_coupon(self, command: AddCouponCommand) -> Coupon:
        """Planned: normalize the code, validate terms, and reject duplicate codes."""
        raise FeatureNotImplemented("Coupon creation")

    def delete_coupon(self, code: str) -> None:
        """Deactivate for new bookings without modifying existing ride snapshots."""
        raise FeatureNotImplemented("Coupon deletion")

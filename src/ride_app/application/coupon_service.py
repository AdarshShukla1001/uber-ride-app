"""Coupon creation and deactivation use-case boundary."""

from ride_app.application.contracts import AddCouponCommand
from ride_app.application.ports import CouponRepository, MutationGuard
from ride_app.domain.models import Coupon
from ride_app.domain.validation import normalized_code, require


class CouponService:
    """Manage catalog availability without changing terms captured by existing rides."""

    def __init__(self, coupons: CouponRepository, guard: MutationGuard) -> None:
        self._coupons = coupons
        self._guard = guard

    def add_coupon(self, command: AddCouponCommand) -> Coupon:
        """Inactive codes remain reserved so deleting cannot silently reuse a code."""
        with self._guard.exclusive():
            require(
                self._coupons.find_by_code(command.code) is None,
                "DUPLICATE_COUPON",
                "Coupon code already exists.",
            )
            coupon = Coupon(command.code, command.terms)
            self._coupons.save(coupon)
            return coupon

    def delete_coupon(self, code: str) -> None:
        """Deactivate for new bookings without modifying existing ride snapshots."""
        code = normalized_code(code, "code", "INVALID_COUPON")
        with self._guard.exclusive():
            coupon = self._coupons.find_by_code(code)
            require(coupon is not None, "COUPON_NOT_FOUND", "Coupon does not exist.")
            self._coupons.save(coupon.deactivate())

# Ride Hailing Backend — Product Requirements

Status: mandatory behavior and all four bonuses implemented through the shared CLI/API core. Configurable rates/upgrades, SUV, and flat coupons are supported. See section 10 for extension behavior.

## 1. Purpose and source

Build a Python ride-hailing backend exposed through an interactive CLI and an HTTP API. Demonstrate correct business behavior, understandable domain modeling, test coverage, and small, localized extensions during a machine-coding interview.

Source: `/Users/adarshshukla/Downloads/coding_assignment_round_2.pdf` (three pages). The assignment provides a two-hour implementation window and a 30-minute demo. It permits any language, CLI or API, and in-memory storage. The user has selected Python and requested both CLI and API. This document records the proposed product decisions; the source document is reference material, not authorization to begin implementation.

## 2. Success criteria

- All mandatory assignment behavior works through shared application services.
- Both local interactive CLI and API expose the mandatory operations.
- Pricing, matching, upgrades, coupons, completion, and histories behave deterministically.
- Automated tests cover the required pricing cases and critical workflow failures.
- A repeatable demo and short README explain assumptions, design trade-offs, limitations, and actual AI usage.
- A new rate tier, car type, or discount type can be introduced without rewriting booking orchestration.

## 3. Scope and priorities

### Mandatory assignment scope

1. Register users.
2. Register drivers and their cabs.
3. Update cab locations.
4. Book an available driver within a configured radius.
5. End a ride and return its cost.
6. Apply tiered pricing and a minimum fare.
7. Show ongoing and completed rides for a user and for a driver.
8. Support Hatchback and Sedan with different rates.
9. Upgrade a Hatchback request to a Sedan at no extra cost when no eligible Hatchback is available.
10. Add, delete, and apply valid coupon codes at booking.
11. Deliver automated pricing tests and a short README.

### User-selected delivery scope

- Python implementation.
- Interactive standalone CLI, repeatable demo command, and HTTP API.
- Shared application core and consistent behavior across interfaces.

### Bonus or deferred scope

The user authorized bonus implementation. Surge pricing, nearest/highest-rated matching, cancellation fees, and in-process concurrency safety are implemented. CLI remote mode remains optional. Configuration and extension semantics are specified in section 10.

### Out of scope

Frontend, live maps, route providers, payments, authentication, dispatch acceptance, persistent database, distributed systems, multi-worker deployment, notifications, and production GPS tracking.

## 4. Explicit product assumptions

These decisions resolve details absent from the assignment and must appear in the implementation README.

| Topic | Baseline decision |
| --- | --- |
| Driver and cab | One cab per driver; driver registration supplies cab type, registration number, and initial location. |
| Availability | Registered drivers are available when not assigned to an ongoing ride. No separate online/offline state. |
| Ride start | Successful booking starts the ride immediately. |
| Active rides | At most one ongoing ride per user and per driver. |
| Coordinates | Latitude and longitude in degrees; validate finite values and geographic ranges. |
| Decimal limits | Arithmetic uses Python Decimal's default precision; amounts outside supported precision are rejected. |
| Matching distance | Haversine distance in kilometers. |
| Search radius | Application configuration, default 5 km; boundary inclusive. This default is an assumption. |
| Matching order | Eligible requested-type drivers first; nearest distance by default, or configured highest rating; deterministic ties. |
| Upgrade | Ordered configurable routes within the same radius; defaults allow Hatchback to Sedan only. |
| Trip distance | Completion supplies a finite, nonnegative distance in kilometers. It is trusted exercise input, independent of straight-line matching distance. |
| Completion location | Completion supplies the drop-off coordinates; update the cab location there. |
| Minimum fare | A pre-discount fare floor, not an additive base charge. |
| Coupon count | Zero or one coupon per ride. |
| Coupon timing | Validate and snapshot terms at booking; apply the discount to the final subtotal at completion. |
| Coupon validity | Coupon exists and is active, with valid configured terms. No expiry, usage limits, or per-user restrictions initially. |
| Coupon deletion | Soft-deactivate for future bookings; existing ride snapshots remain valid. |
| Coupon codes | Trim and uppercase consistently. Reject duplicate codes, including previously deleted codes, in the baseline. |
| Repeated completion | For a valid repeat request, return the stored receipt without changing fare, distance, location, or timestamps. |
| Histories | Read from canonical ride records; newest first, with stable ID tie-breaker. |
| Registration | Names must be nonempty; cab registration numbers must be unique after normalization. No phone or email uniqueness model. |
| Persistence | State lasts only for the process lifetime. |

## 5. Pricing specification

Rate cards are configuration data. Use these proposed initial values; only the Hatchback example is taken from the assignment's sample, which does not itself assign that example to a particular car type.

| Car type | Minimum | First 2 km | Above 2 through 5 km | Above 5 km |
| --- | ---: | ---: | ---: | ---: |
| Hatchback | INR 50 | INR 10/km | INR 8/km | INR 5/km |
| Sedan | INR 70 | INR 14/km | INR 11/km | INR 8/km |
| SUV | INR 100 | INR 20/km | INR 16/km | INR 12/km |

The Sedan/SUV values and attribution of the sample rates to Hatchback are proposed assumptions.

Tiers are cumulative marginal charges. Fractional distances are prorated; there are no gaps between 2 and 3 km or between 5 and 6 km.

For Hatchback distance `d`:

```text
distance_charge = 10 * min(d, 2)
                + 8 * min(max(d - 2, 0), 3)
                + 5 * max(d - 5, 0)
base = max(minimum_fare, distance_charge)
subtotal = round_money(base * captured_surge_multiplier)
discount = min(subtotal, coupon_discount(subtotal))
total = subtotal - discount
```

Use decimal arithmetic. Round the aggregate distance charge to two decimal places using ROUND_HALF_UP, apply the minimum, multiply by captured surge and round to two decimals, round the coupon discount to two decimal places, cap it at the subtotal, then subtract. The receipt must reconcile exactly: distance charge + minimum adjustment + surge adjustment - discount = total.

Coupon creation supports percentages strictly greater than 0 and at most 100, and positive flat amounts with whole-paise precision. Both are capped at the post-surge subtotal.

Always use the requested car type's snapshotted rate card, including free upgrades. Coupons can reduce the payable fare below the pre-discount minimum, but never below zero.

### Reference examples

| Scenario | Expected result |
| --- | --- |
| Hatchback, 0 km | Distance charge INR 0; subtotal INR 50. |
| Hatchback, 5 km | Distance charge INR 44; subtotal INR 50. |
| Hatchback, 6 km | Distance charge INR 49; subtotal INR 50. |
| Hatchback, 10 km | Distance charge and subtotal INR 69. |
| Hatchback, 10 km, 10% coupon | Discount INR 6.90; final INR 62.10. |
| Hatchback, 1 km, 10% coupon | Subtotal INR 50; final INR 45. |
| Sedan, 10 km | Subtotal INR 101. |
| Hatchback request fulfilled by Sedan, 10 km | Subtotal INR 69; assigned type remains Sedan. |

## 6. Functional acceptance criteria

### Registration and location

- Valid registration returns a generated ID.
- Driver registration records a cab, supported car type, and valid initial location.
- Invalid fields and duplicate cab registrations fail without partial records.
- Location updates affect subsequent matching; updates during ongoing rides do not determine billed distance.

### Booking

- Validate user, requested type, pickup, active-ride restriction, and optional coupon before assignment.
- Ignore busy drivers and drivers outside the radius.
- Prefer an eligible Hatchback over a nearer Sedan for a Hatchback request.
- If no eligible Hatchback exists, choose an eligible Sedan and retain Hatchback billing terms.
- If no eligible vehicle exists, return NO_DRIVER_AVAILABLE without creating a ride or reserving a driver.
- Successful booking returns ride ID, driver ID, requested and assigned types, upgrade indicator, status, and captured pricing/coupon terms. It does not claim a final fare before trip distance is known.
- Failed booking must not leave an assigned driver or an orphan ride.

### Completion and history

- Complete only an existing ongoing ride, or return the stored result for an already completed ride.
- Calculate with booking-time terms, store an itemized receipt, mark completed, update location, and release the driver.
- Invalid completion leaves the ongoing ride and assignment unchanged.
- User and driver histories expose the same canonical ride state and receipt.
- Unknown user or driver history requests return not-found; known entities without rides return an empty list.

### Coupons

- Add a valid percentage or flat coupon; reject empty codes, duplicates, and invalid terms.
- Delete an existing coupon by deactivation; repeated deletion is successful, unknown code is not-found.
- Missing, deleted, or invalid coupons cause booking failure when explicitly supplied.
- Deletion after booking does not invalidate captured terms.

## 7. Interface contract

| Operation | Interactive CLI | HTTP |
| --- | --- | --- |
| Register user | `user register` | `POST /users` |
| Register driver | `driver register` | `POST /drivers` |
| Update location | `driver location` | `PATCH /drivers/{id}/location` |
| Book ride | `ride book` | `POST /rides` |
| Cancel ride | `ride cancel` | `POST /rides/{id}/cancel` |
| Complete ride | `ride end` | `POST /rides/{id}/complete` |
| View ride | `ride show` | `GET /rides/{id}` |
| User history | `user rides` | `GET /users/{id}/rides` |
| Driver history | `driver rides` | `GET /drivers/{id}/rides` |
| Add coupon | `coupon add` | `POST /coupons` |
| Delete coupon | `coupon delete` | `DELETE /coupons/{code}` |

Proposed process entry points:

```text
python -m ride_app cli
python -m ride_app demo
python -m ride_app serve
```

The local CLI retains state inside one interactive session. The demo runs a scenario in one process. The API uses one worker and retains state until exit. Separate processes do not share memory. Optional remote CLI mode must call the API rather than pretend to share local dictionaries.

API fare amounts and minimum fares are decimal strings with two fractional digits. Per-kilometer rates, percentages, and trip distances retain their supplied decimal precision. Use UTC ISO-8601 timestamps. Return machine-readable errors with a stable code, message, and optional field details. CLI presents equivalent errors and keeps interactive sessions running after invalid commands; failed noninteractive scripts return a nonzero exit status.

## 8. Verification and demonstration

Required tests: raw tier boundaries and fractional distances, minimum floor, car-type rates, coupons, rounding, and free upgrades. Test raw tier amounts separately because the minimum fare can hide tier mistakes.

Workflow tests: radius boundary, no driver, busy driver, deterministic selection, requested-type priority, duplicate active ride, invalid coupon without mutation, deletion after booking, captured rates, driver release, repeated completion, and consistent histories. Test simultaneous bookings for one driver if the concurrency boundary is implemented.

Smoke-test both CLI and API against shared expected outcomes. Use a deterministic demo with normal booking, a free upgrade, coupon application, completion, histories, and a failure case.

The assignment demo allocates 8 minutes to behavior, 8 minutes to design, 10 minutes to a live extension, and 4 minutes to questions. Prepare explanations for pricing boundaries, snapshots, matching priority, storage limitations, and AI decisions.

## 9. Implementation plan and definition of done

| Window | Planned outcome |
| --- | --- |
| 0–10 min | Confirm assumptions, scaffolding, contracts. |
| 10–30 min | Models, pricing, coupons, and pricing tests. |
| 30–45 min | Storage, registration, location updates. |
| 45–75 min | Matching, booking, completion, histories, workflow tests. |
| 75–100 min | Interactive CLI, API, demo. |
| 100–120 min | Integration checks, fixes, README, final verification. |

The schedule is a target, not a reason to skip mandatory behavior or tests. Defer optional features first. Definition of done: mandatory acceptance criteria pass, both interfaces run using documented commands, tests pass, no placeholder business behavior remains, and README covers assumptions, trade-offs, future improvements, and truthful AI usage. Make incremental meaningful commits during implementation when authorized by the implementation task.

See [backendrules.md](backendrules.md) for engineering constraints and class diagrams.


## 10. Implemented extensions and explicit assumptions

This section extends the baseline two-category, percentage-only scope above. User authorization covers the four assignment bonuses plus customization support.

- TOML startup configuration selects matching, surge, cancellation, radius, full per-category rate overrides and ordered assignment routes. Defaults preserve original pricing and matching. Unknown fields and invalid values fail startup. No hot reload; restarting clears in-memory state.
- Car types include SUV at assumed rates 100 minimum / 20, 16, 12 per km. Default SUV requests match SUV only; Hatchback still falls back only to Sedan. Additional fallback routes require explicit configuration. Assignment permissions are captured alongside requested-type rates, so entity validation does not duplicate fixed category pairs.
- Driver ratings are optional trusted registration inputs in [0, 5], not a customer-rating subsystem. Highest-rated ranking prefers rated candidates, descending rating, then nearest distance, then ID. Eligibility and fallback precedence still apply before ranking.
- Surge is disabled by default. The local provider counts ongoing same-requested-type rides with pickups within the search radius plus this request, and compatible available drivers within that radius. It is an active-ride demand proxy. Compute `min(maximum, 1 + max(0, demand/max(1,supply)-1)*sensitivity)` before reservation, with default maximum 3 and sensitivity 0.5. Policy limits are maximum 1–100 and sensitivity 0–100. A zero-supply quote never overrides matching failure. Capture the multiplier at booking. Minimum is applied before surge; coupons are applied after surge; free upgrades still use requested-type rates.
- Flat coupons are positive whole-paise amounts, capped at the surged subtotal. Existing percentage API/CLI inputs remain accepted. Explicit HTTP discount_type/value must not be combined with legacy percentage.
- Cancellation transitions ONGOING to CANCELLED. Since booking starts the ride immediately, the grace clock starts at booking; there is no separate dispatch/arrival lifecycle. Default is free through exactly 120 seconds, INR 20 afterwards. Configurable free policy records zero fee terms. No coupon/surge adjustment or distance fare applies on cancellation; it records a fee without collecting payment.
- Cancellation has its own timestamp, fee and reason, no completion receipt/distance/drop-off. Keep latest cab location. Release the exact ride assignment once. A repeat returns the saved cancellation even after driver reuse. Reject completion of cancelled rides and cancellation of completed rides. All histories include cancelled rides.
- Rates, coupons, surge multiplier, cancellation terms and ordered allowed types are immutable booking snapshots. Policy implementations are fixed for an application lifetime; policy hot swapping is unsupported.
- All mutation flows share the existing lock. Tests cover concurrent bookings, cancellation/completion contention and duplicate cancellations. No cross-process or durable transaction guarantee is claimed.

See `docs/customization.md` for extension recipes and the SOLID responsibility map; `config/example.toml` is an executable example.

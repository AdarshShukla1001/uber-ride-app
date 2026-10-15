# Ride Hailing Backend

Python 3.12 backend with an interactive CLI and FastAPI interface over the same application services. Supports registration, cab locations, booking, completion, tiered pricing, free upgrades, percentage/flat coupons, surge, rating-based matching, cancellation, and user/driver histories.

## Setup and run

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -e '.[dev]'
.venv/bin/python -m ride_app demo
.venv/bin/python -m ride_app cli
.venv/bin/python -m ride_app serve
```

The existing local `.venv` is already initialized. `ride-app` is an equivalent installed console entry point. Dependency ranges live in `pyproject.toml`; `requirements-dev.lock` captures the verified development environment on macOS arm64. Regenerate it from a clean environment with `pip freeze --exclude-editable` after dependency changes.

The API binds to `127.0.0.1:8000`. Explore [interactive API documentation](http://127.0.0.1:8000/docs) or `GET /health`. Override the address with `serve --host 127.0.0.1 --port 8001`.

CLI sessions keep state until exit. Separate CLI and API processes have separate data; run the API with one worker. State disappears on restart.

## CLI walkthrough

```text
user register --name Alice
driver register --name Bob --registration-number KA01AB1234 --type sedan --lat 12.97 --lng 77.59
coupon add --code SAVE10 --percentage 10
```

Copy the generated user ID from the output into the next command, then copy the returned ride ID into subsequent commands:

```text
ride book --user USER_ID --type hatchback --lat 12.97 --lng 77.59 --coupon SAVE10
ride end --ride RIDE_ID --distance-km 10 --lat 13.01 --lng 77.64
ride show --ride RIDE_ID
user rides --user USER_ID
driver rides --driver DRIVER_ID
coupon delete --code SAVE10
driver location --driver DRIVER_ID --lat 12.97 --lng 77.59
help
exit
```

With only a Sedan available, this Hatchback request upgrades for free. A 10 km trip with SAVE10 costs INR 62.10 at Hatchback rates. `demo` runs a repeatable scenario including a minimum fare, upgrade, captured coupon after deletion, histories, and expected failure cases. IDs and timestamps are fixed in the demo only.

Invalid commands print errors and keep the session alive. The process exits nonzero if any command failed, making redirected scripts verifiable.

## API operations

| Action | Endpoint |
| --- | --- |
| Register user | `POST /users` |
| Register driver and cab | `POST /drivers` |
| Update cab location | `PATCH /drivers/{id}/location` |
| Book ride | `POST /rides` |
| Cancel ride | `POST /rides/{id}/cancel` |
| Complete ride | `POST /rides/{id}/complete` |
| View ride | `GET /rides/{id}` |
| User / driver histories | `GET /users/{id}/rides`, `GET /drivers/{id}/rides` |
| Add / delete coupon | `POST /coupons`, `DELETE /coupons/{code}` |

Use the schemas in `/docs` for request bodies. For example, coupon creation accepts `{"code":"SAVE10","percentage":"10"}`. Completion accepts `{"distance_km":"10","dropoff":{"latitude":13.01,"longitude":77.64}}`. Supply decimal inputs as strings to preserve precision. Fare amounts are two-decimal strings; timestamps use timezone-aware UTC.

Errors use `{"error":{"code":"...","message":"..."}}`, with field details for malformed input. Unknown entities return 404, assignment/duplicate conflicts and no driver return 409, and invalid inputs/coupons return 422.

## Design and assumptions

- Immutable domain records enforce validation and return replacements for transitions. Services stage all fallible validation before storing related ride/driver changes under a shared lock. In-memory writes have no external IO; this is not a rollback transaction or crash-durable store.
- Domain policies do not import FastAPI or Pydantic. Repository protocols allow storage substitution. HTTP output schemas and CLI rendering remain adapter concerns.
- One cab per driver. Booking immediately starts a ride. Each user and driver can have at most one ongoing ride. Availability derives from assignment. Cancellation releases both and appears in histories.
- Matching uses Haversine distance with an inclusive configurable 5 km default radius. Requested type takes priority, then Hatchback-to-Sedan fallback. Ranking defaults to nearest driver, then stable ID; highest-rated ranking is selectable through configuration. Ordered upgrade routes are configurable, with requested-type billing preserved.
- Billing follows requested type, including upgrades. Immutable rates, coupons, surge multiplier, cancellation terms, and allowed assignment types are captured at booking; later data changes do not reprice the trip.
- Completion uses supplied, trusted trip distance; GPS updates do not determine billed distance. Completion updates the cab to drop-off and releases its assignment. Valid repeat completion returns the stored result without changing driver state.
- Names are trimmed; coupon codes and cab registration numbers are trimmed and uppercased. Deleted coupon codes remain reserved. Coupons are percentages above 0 and at most 100 or positive flat amounts in whole paise, one per ride, with no expiry or usage limit.

| Rate card | Minimum | First 2 km | Above 2–5 km | Above 5 km |
| --- | ---: | ---: | ---: | ---: |
| Hatchback | INR 50 | INR 10/km | INR 8/km | INR 5/km |
| Sedan | INR 70 | INR 14/km | INR 11/km | INR 8/km |
| SUV | INR 100 | INR 20/km | INR 16/km | INR 12/km |

These are disclosed exercise assumptions: the source provides one example schedule, not separate car-type schedules. Tiers are marginal and fractional distances are prorated. Round the combined distance charge with ROUND_HALF_UP, apply the minimum, multiply by captured surge and round, round and cap the coupon discount, then subtract. Coupons may reduce fare below the minimum, never below zero. Arithmetic uses Decimal's default precision; unsupported magnitudes are rejected.

The full product contract is in [.agent/prd.md](.agent/prd.md); architecture and class diagrams are in [.agent/backendrules.md](.agent/backendrules.md).

## Configuration and bonus behavior

Start with defaults (nearest matching, no surge) or use the annotated example:

```bash
.venv/bin/python -m ride_app cli --config config/example.toml
.venv/bin/python -m ride_app serve --config config/example.toml
```

The example enables highest-rated matching, demand/supply surge, SUV fallbacks and a fourth Hatchback tier. Configuration is validated once at startup; changes require a restart, which also clears this in-memory application's data. Unknown fields and invalid policy names fail startup. [Customization guide](docs/customization.md) maps each change to configuration, a policy, or a domain change and explains SOLID.

- **Surge:** local demand is nearby ongoing rides of the requested type plus the incoming request; supply is compatible available cabs within the search radius. This is an exercise proxy for demand, not real request telemetry. Multiplier = `min(maximum, 1 + max(0, demand / max(1, supply) - 1) * sensitivity)`, captured before assignment. No available driver still means no booking.
- **Matching:** highest-rated considers eligible requested-type candidates first, then configured fallback types. Rated drivers precede unrated drivers; ties use distance then ID. Ratings are optional decimals from 0 to 5.
- **Cancellation:** booking starts a ride immediately. Ongoing rides may be cancelled free through 120 seconds, then INR 20 by default. Grace period/fee and free policy are configurable. Cancellation retains the latest cab location, records a separate fee, and releases the assignment once. Coupons and surge do not affect cancellation fees. Completed rides cannot be cancelled; cancelled rides cannot be completed. Repeated cancellation returns the saved result.
- **Concurrency:** one shared lock protects booking, completion, cancellation and related changes. This guarantee applies to one application context in one process.

Additional CLI examples:

```text
driver register --name Sam --registration-number KA02 --type suv --rating 4.8 --lat 0 --lng 0
coupon add --code FLAT20 --flat 20
ride cancel --ride RIDE_ID --reason "Plans changed"
```

The API accepts `{"code":"FLAT20","discount_type":"flat","value":"20"}` and continues to accept legacy `{"code":"SAVE10","percentage":"10"}`. Do not combine formats. Cancellation accepts `POST /rides/{id}/cancel` with `{}` or `{"reason":"Plans changed"}`. Responses add rating, captured terms, `surge_adjustment`, and optional `cancellation` details; `cancelled` is a new terminal status.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
.venv/bin/python -m compileall -q src
.venv/bin/python -m pip check
```

Tests cover raw tier boundaries, rounding, minimum fares, car-type rates, coupons, upgrade billing, matching, state preservation on failure, snapshots, idempotent completion, histories, concurrent booking, and both interfaces. See [tests/README.md](tests/README.md).

## Trade-offs and further work

Linear driver/history scans and one process-wide lock favor correctness and clarity at interview scale. A database adapter would need transactions and uniqueness constraints; adding repository implementations alone is insufficient. Geographic indexing would improve matching at scale.

Remote CLI mode, persistent storage, authentication, real demand telemetry, rating collection, and trusted trip-distance collection remain future work. Ratings are trusted registration input for this exercise. Cancellation records a fee; no payment collection occurs.

## AI usage

AI assisted with assignment analysis, architecture, scaffold, implementation, comments, and tests. Changes prompted during review included independent raw-tier tests because minimums mask errors, keeping requested and assigned car types separate, retaining immutable booking snapshots, and checking repeat completion before touching driver state. Speculative vehicle subclass hierarchies and distributed infrastructure were omitted to keep the solution explainable. Validation, pricing, matching, and workflow tests were run incrementally; adapter tests then verified the same behavior through CLI and HTTP.

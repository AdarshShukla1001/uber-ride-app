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

## Assumptions

- **Fleet and Driver Model:** One cab per driver. Driver availability is derived strictly from assignment (`active_ride_id is None`) rather than a mutable status flag. Each rider and driver can participate in at most one ongoing ride at any time.
- **Geographic Model:** Matching uses great-circle Haversine distance with an inclusive configurable radius (default 5 km). Geographic coordinates are validated within $[-90, 90]$ latitude and $[-180, 180]$ longitude using finite floating-point numbers.
- **Trusted Trip Distance:** Trip billing uses the distance reported at completion; GPS coordinates do not calculate billed distance, but update the driver's cab location upon drop-off.
- **Pricing Schedule & Rate Cards:** The problem statement provided a single tiered example (Min ₹50, 0–2 km @ ₹10/km, 3–5 km @ ₹8/km, 6+ km @ ₹5/km). We interpreted this as the Hatchback schedule and established an explicit, higher tier schedule for Sedan (Min ₹70, 0–2 km @ ₹14/km, 2–5 km @ ₹11/km, 5+ km @ ₹8/km) and SUV (Min ₹100, 0–2 km @ ₹20/km, 2–5 km @ ₹16/km, 5+ km @ ₹12/km). Tiers are marginal and prorated continuously.
- **Free Upgrade Guarantee:** If a requested vehicle class (e.g., Hatchback) has no available drivers within the radius, the system searches the upgrade route (Hatchback $\to$ Sedan $\to$ SUV). Upgraded trips are billed strictly using the *requested* car type's rate card.
- **Coupon Lifecycle:** Coupon codes are normalized to uppercase. Deleted coupons are soft-deactivated (`active=False`) so that codes remain reserved and cannot be recreated with altered terms. A booking captures an immutable snapshot of coupon terms; subsequent coupon deletion never retroactively changes in-flight or completed fares.
- **Financial Precision:** All money amounts and billed trip distances use Python's `Decimal` with explicit `ROUND_HALF_UP` to the nearest paise (`Decimal("0.01")`). Binary floating-point money is strictly forbidden.
- **In-Memory Storage Scope:** Per the exercise specification, storage is in-memory dictionaries. Process isolation means standalone CLI and API processes hold independent state, and Uvicorn runs with a single worker.

| Rate card | Minimum | First 2 km | Above 2–5 km | Above 5 km |
| --- | ---: | ---: | ---: | ---: |
| Hatchback | INR 50.00 | INR 10.00/km | INR 8.00/km | INR 5.00/km |
| Sedan | INR 70.00 | INR 14.00/km | INR 11.00/km | INR 8.00/km |
| SUV | INR 100.00 | INR 20.00/km | INR 16.00/km | INR 12.00/km |

## Key Design Decisions and Trade-offs

1. **Hexagonal Architecture (Ports & Adapters) with Zero-Dependency Domain:**
   - *Decision:* The domain core (`models.py`, `pricing.py`, `matching.py`, `policies.py`) has zero imports from FastAPI, Pydantic, or storage libraries. Use cases are orchestrated in application services behind structural Protocols (`ports.py`).
   - *Trade-off:* Requires explicit mapping between HTTP schemas, application commands, and domain entities. This adds slight boilerplate but guarantees complete decoupling: CLI and API share identical business rules, and swapping storage requires zero domain changes.
2. **Immutable Domain Entities (`dataclass(frozen=True, slots=True)`):**
   - *Decision:* All domain records (`User`, `Driver`, `Cab`, `Ride`, `BookingTerms`, `FareBreakdown`) are immutable. State transitions return fresh copies via `replace()`.
   - *Trade-off:* Slightly higher memory churn during transitions, but completely eliminates side-effect bugs and race conditions where partially mutated objects leak during failed operations.
3. **Staged Mutations under a Single Reentrant Lock (`InProcessMutationGuard`):**
   - *Decision:* All state-changing operations across multi-entity boundaries (Driver + Ride + Coupon) synchronize on a single `threading.RLock()`. All fallible business validations run *before* repository writes.
   - *Trade-off:* Limits write throughput to a single CPU core, which is intentional and optimal for an interview machine-coding scope. It avoids deadlock hazards and multi-lock race conditions.
4. **Snapshotting Pattern for Financial Contracts (`BookingTerms`):**
   - *Decision:* Rate card tiers, coupon terms, surge multiplier, cancellation terms, and upgrade permissions are snapshotted on the `Ride` at booking time.
   - *Trade-off:* Stores duplicate data per ride record rather than referencing catalog IDs, but provides total isolation against configuration updates, coupon deletion, or dynamic surge fluctuations while a ride is in progress.
5. **Idempotent Completion and Cancellation:**
   - *Decision:* Repeated completion or cancellation requests return the existing saved record immediately.
   - *Trade-off:* Requires terminal status checks at the use-case boundary, but guarantees safety against network retries: a completed ride will never re-release or relocate a driver who may have already taken a subsequent trip.

## What We Would Do Differently with More Time

1. **Distributed Spatial Indexing (Uber H3 / S2 Geometry):**
   - Currently, driver discovery uses a linear Haversine scan $O(N)$ over all available drivers. In production, driver GPS pings would update an H3 hexagonal spatial index (or Redis GEO / PostGIS), enabling $O(1)$ radius lookups by querying neighboring hexagon rings.
2. **Crash-Durable Persistence & Transactional Boundaries:**
   - Replace in-memory dictionaries with PostgreSQL/CockroachDB. Replace `InProcessMutationGuard` with database-level isolation (`SELECT ... FOR UPDATE` or optimistic locking with record versions) to support multi-worker, horizontally scaled API instances.
3. **Real-Time Request Telemetry for Dynamic Surge:**
   - Our surge implementation calculates demand using active nearby rides as a proxy. In production, an asynchronous event pipeline (Kafka/Flink) would track unfulfilled ride requests, app opens, and ETA elasticity to produce predictive surge grids.
4. **Authentication, Driver Payouts & Webhook Ingestion:**
   - Implement JWT-based RBAC (Riders vs Drivers vs Admins), automated driver payout ledger accounting, and external payment gateway webhooks (Stripe/Razorpay) for live ride settlement and cancellation fees.
5. **Live Turn-by-Turn GPS Telemetry & OSRM Routing:**
   - Replace user-supplied trusted distance with real-time waypoint streaming and road-network distance calculation (e.g., OSRM/Valhalla) rather than Euclidean/Haversine estimates.

## AI Collaboration and Ground Rules Reflection

- **What was prompted for:**
  - Generating initial boilerplate for pure mathematical formulas (Haversine great-circle distance).
  - Drafting initial Pydantic HTTP schema definitions and argparse CLI subparser structure.
  - Generating comprehensive tabular test fixtures for raw tier boundaries, edge distances, and floating-point money traps.
- **What was critically reviewed, rejected, or rewritten:**
  - *Rejected Compounding Tier Rounding:* Initial AI suggestions rounded intermediate distance charges at each tier boundary. This was rejected because rounding before summing compounds fractional errors. We rewrote it to sum unrounded marginal segments and apply `ROUND_HALF_UP` exactly once.
  - *Rejected Mutable Entity Lifecycles:* The AI initially generated mutable OOP classes with in-place mutation methods (e.g. `driver.status = 'busy'`). This was rewritten to immutable frozen dataclasses returning new instances via `replace()` to ensure atomicity.
  - *Rejected Shared/Live Catalog Lookups at Completion:* AI proposed querying the coupon and rate-card catalogs during `complete_ride`. We rejected this design and introduced `BookingTerms` snapshots to eliminate temporal coupling when coupons are deleted midway through a trip.
  - *Rejected Fragmented Multi-Locking:* AI suggested separate threading locks for each repository. We rejected this due to deadlock hazards during multi-record booking/completion workflows and unified synchronization into a single `InProcessMutationGuard`.
  - *Rejected Speculative Vehicle Class Hierarchies:* AI attempted to create abstract vehicle class hierarchies (`class Sedan(Vehicle)`). We rejected this over-engineering in favor of clean `CarType` enums and data-driven `RateCard` catalogs.

## Verification

Run the full automated test suite and linter:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
.venv/bin/python -m compileall -q src
.venv/bin/python -m pip check
```

All 135 unit, workflow, edge-case, and concurrency tests pass. Run `.venv/bin/python -m ride_app demo` to see the repeatable end-to-end acceptance demo scenario.


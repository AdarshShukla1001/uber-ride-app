# Ride Hailing Backend

Python backend scaffold with a shared domain/application core, interactive CLI, and FastAPI adapter.

## Current status

The project structure, typed domain records, command contracts, repository protocols and in-memory adapters, dependency wiring, CLI parser, and HTTP routes are initialized.

Business rules are not implemented yet. Service methods, matching, and pricing raise `FeatureNotImplemented`. API business routes return HTTP 501; CLI commands report `NOT_IMPLEMENTED`. `/health` and API documentation work. Model validation, lifecycle transitions, finalized output schemas, and the end-to-end demo remain implementation work. This is not a completed assignment submission.

## Setup

Use Python 3.12 or newer. The system Python 3.9 on this machine is too old for this project.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -e '.[dev]'
```

`pyproject.toml` declares dependency ranges. `requirements-dev.lock` records the resolved development environment verified with Python 3.12 on macOS arm64. Regenerate it with `pip freeze --exclude-editable` from a clean project virtual environment after dependency changes; do not maintain a second hand-written requirements list.

## Run

```bash
.venv/bin/python -m ride_app --help
.venv/bin/python -m ride_app cli
.venv/bin/python -m ride_app serve
```

API documentation: `http://127.0.0.1:8000/docs`. Health endpoint: `GET /health`.

Example CLI session commands (currently report unimplemented operations):

```text
user register --name Alice
driver register --name Bob --registration-number KA01AB1234 --type hatchback --lat 12.97 --lng 77.59
ride book --user U1 --type hatchback --lat 12.97 --lng 77.59
ride end --ride R1 --distance-km 10 --lat 13.01 --lng 77.64
help
exit
```

The console script `ride-app` exposes the same entry point after installation. `python -m ride_app demo` is reserved and currently exits with an explicit unimplemented error.

## Architecture

```text
src/ride_app/
    domain/          Immutable records, errors, pricing and matching boundaries
    application/     Commands, repository protocols, use-case service skeletons
    infrastructure/  In-memory repositories, rate configuration, shared lock
    interfaces/      CLI parser and HTTP requests/routes
    bootstrap.py     Per-context dependency wiring
    __main__.py      cli / serve / demo entry point
tests/               Verification plan; tests added alongside business behavior
.agent/              Product requirements, class diagrams, engineering rules
```

Application services depend on domain policies and repository protocols. Domain modules have no FastAPI/Pydantic dependencies. Both adapters call the same services. Bootstrap shares repositories and one mutation guard within a context. Stateless calculations remain functions unless a substitutable strategy is justified.

Records are immutable; services will stage replacements rather than mutate shared entities. Ride assignment/release and completion methods will be implemented with invariant tests, rather than leaving unvalidated setters on entities.

## Assumptions and limits

- Each driver has one cab; an active ride determines availability.
- Booking immediately starts a ride; one ongoing ride per user and driver.
- Matching uses a configurable 5 km default radius and nearest eligible requested type, then Hatchback-to-Sedan fallback.
- Upgrades retain requested-type pricing, with rate/coupon snapshots captured at booking.
- Supplied completion distance is trusted exercise input; no route provider is integrated.
- Minimum fare applies before coupons; money uses Decimal and ROUND_HALF_UP.
- Initial coupons are percentages; coupon deletion preserves booked terms.
- Proposed Hatchback rates are INR 50 minimum and INR 10/8/5 per km; proposed Sedan rates are INR 70 minimum and INR 14/11/8 per km, across boundaries 2 km and 5 km.
- In-memory state disappears when the process exits. Standalone CLI and API processes have separate data. Use one API worker. The shared lock provides no distributed coordination or crash durability.

The full decisions and acceptance criteria are in [.agent/prd.md](.agent/prd.md). Architecture and class diagrams are in [.agent/backendrules.md](.agent/backendrules.md).

## Next implementation stages

1. Implement model invariants and pure pricing, with boundary/rounding tests.
2. Implement registration and coupon validation.
3. Implement geographic matching, booking, completion, histories, and atomic state changes.
4. Finalize output schemas, verify both adapters, and build the deterministic demo.

With more time: persistence with transactions, authentication, trusted distance collection, and optional surge/cancellation/remote CLI support after mandatory behavior is solid.

## Verification

```bash
.venv/bin/python -m compileall -q src
.venv/bin/python -m ruff check src
.venv/bin/python -m ruff format --check src
```

The test plan is in [tests/README.md](tests/README.md). Run `.venv/bin/python -m pytest` after behavior tests are introduced; there is no business test suite yet.

## AI usage

AI helped analyze the assignment, propose the Python architecture, write the planning documents, and initialize this scaffold. The design was adjusted to keep CLI state within one session, separate requested and assigned car types, and use immutable records for staged writes. This note should evolve to record actual corrections and review decisions during implementation.

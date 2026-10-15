# Verification

Run `.venv/bin/python -m pytest -q` from the repository root.

| Module | Coverage |
| --- | --- |
| `test_domain.py` | Core validation, immutable records, valid lifecycle states, receipt reconciliation. |
| `test_pricing.py` | Raw tiers and fractional boundaries, minimums, rounding, coupons, car-type rates, data-driven tier extension. |
| `test_matching.py` | Haversine geometry, inclusive radius, busy drivers, type priority, fallback, deterministic and pluggable ranking. |
| `test_ride_workflows.py` | Registration, uniqueness, booking/completion, snapshots, failures without mutation, driver reuse, histories, simultaneous booking. |
| `test_api.py` | Lifecycle, upgrade billing, serialization, validation/errors, health and OpenAPI. |
| `test_extensions.py` | Config loading/rejection, highest-rated selection, surge formula and local provider, flat discounts, SUV routes, cancellation boundaries/retries, cancel/complete races, and CLI/API bonus contracts. |
| `test_cli.py` | Session persistence, lifecycle, recoverable input errors, EOF/help, demo. |

Tests use fresh contexts and injected IDs/time. Concurrent booking uses a barrier rather than sleep-based scheduling. Both receipt components and final totals are asserted, because the minimum fare can hide tier bugs.

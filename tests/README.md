# Planned verification

Business tests will be added with each implemented behavior; no placeholder passing tests.

| Test module | Behavior to cover |
| --- | --- |
| `test_pricing.py` | Raw tiers, boundaries, fractional distances, minimums, rounding, coupon calculation, car-type rates, upgrade pricing. |
| `test_matching.py` | Radius inclusion, busy drivers, type priority, fallback, deterministic tie-breaker. |
| `test_ride_workflows.py` | Registration, uniqueness, booking atomicity, one active ride, captured terms, completion, idempotency, driver reuse, histories, simultaneous booking. |
| `test_api.py` | Successful lifecycle, validation, error mapping, response serialization. |
| `test_cli.py` | Session persistence, command dispatch, recoverable errors, scripted exit codes. |

Use a fresh application context per test and injected IDs/time for repeatability. See `.agent/prd.md` for acceptance criteria.

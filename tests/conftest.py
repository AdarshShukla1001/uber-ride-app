"""Fresh context and deterministic IDs/time keep tests independent and repeatable."""

from datetime import UTC, datetime
from itertools import count

import pytest

from ride_app.bootstrap import create_application


@pytest.fixture
def app():
    ids = count(1)
    return create_application(
        new_id=lambda: f"id-{next(ids):03}",
        clock=lambda: datetime(2026, 10, 15, 12, tzinfo=UTC),
    )

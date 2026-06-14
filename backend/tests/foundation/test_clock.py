from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mutualfund.foundation.clock import FixedClock, SystemClock


def test_system_clock_is_tz_aware() -> None:
    assert SystemClock().now().tzinfo is not None


def test_fixed_clock_returns_set_moment() -> None:
    moment = datetime(2026, 6, 14, tzinfo=timezone.utc)
    assert FixedClock(moment).now() == moment


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 6, 14))  # noqa: DTZ001

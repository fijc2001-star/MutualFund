"""Injectable clock so backtests/sandbox/tests get deterministic time (ARCHITECTURE §3.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Wall-clock time, always timezone-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic clock for tests and replay."""

    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def set(self, moment: datetime) -> None:
        self._moment = moment

"""Market-data DTOs. Decimal for prices, tz-aware datetimes throughout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from ..foundation.instrument import Instrument


class TimeFrame(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"


@dataclass(frozen=True, slots=True)
class Quote:
    instrument: Instrument
    bid: Decimal
    ask: Decimal
    last: Decimal
    ts: datetime

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)


@dataclass(frozen=True, slots=True)
class Bar:
    instrument: Instrument
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class OptionContract:
    instrument: Instrument
    bid: Decimal
    ask: Decimal
    last: Decimal
    implied_volatility: Decimal | None = None
    delta: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OptionChain:
    underlying: str
    contracts: list[OptionContract] = field(default_factory=list)

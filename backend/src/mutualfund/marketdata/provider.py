"""The MarketDataProvider interface — swappable per REQUIREMENTS §6.

First implementation: ThinkorSwim/Schwab. Any other provider (Polygon, Databento, ...)
plugs in behind this protocol; the FakeProvider backs dev + tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Protocol

from ..foundation.instrument import Instrument
from .types import Bar, OptionChain, Quote, TimeFrame


class MarketDataProvider(Protocol):
    name: str

    async def quote(self, instrument: Instrument) -> Quote: ...

    async def bars(
        self, instrument: Instrument, timeframe: TimeFrame, start: datetime, end: datetime
    ) -> list[Bar]: ...

    async def option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> OptionChain: ...

    def stream(self, instruments: list[Instrument]) -> AsyncIterator[Quote]: ...

"""Deterministic in-memory provider for dev + tests.

Unblocks all downstream work without external credentials (IMPLEMENTATION_PLAN §5).
Prices are generated deterministically from the symbol so tests are repeatable.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from ...foundation.instrument import AssetClass, Instrument
from ..types import Bar, OptionChain, OptionContract, Quote, TimeFrame

_TF_DELTA: dict[TimeFrame, timedelta] = {
    TimeFrame.M1: timedelta(minutes=1),
    TimeFrame.M5: timedelta(minutes=5),
    TimeFrame.M15: timedelta(minutes=15),
    TimeFrame.H1: timedelta(hours=1),
    TimeFrame.D1: timedelta(days=1),
}


def _seed_price(symbol: str) -> Decimal:
    digest = hashlib.sha256(symbol.encode()).hexdigest()
    # Map first 4 hex chars → a base price in [50, 50+~655].
    base = int(digest[:4], 16) % 600
    return Decimal(50 + base)


class FakeProvider:
    name = "fake"

    def __init__(self, spread: Decimal = Decimal("0.02")) -> None:
        self._spread = spread

    async def quote(self, instrument: Instrument) -> Quote:
        last = _seed_price(instrument.symbol)
        half = self._spread / Decimal(2)
        return Quote(
            instrument=instrument,
            bid=last - half,
            ask=last + half,
            last=last,
            ts=datetime.now(UTC),
        )

    async def bars(
        self, instrument: Instrument, timeframe: TimeFrame, start: datetime, end: datetime
    ) -> list[Bar]:
        step = _TF_DELTA[timeframe]
        base = _seed_price(instrument.symbol)
        bars: list[Bar] = []
        ts = start
        i = 0
        while ts <= end:
            drift = Decimal(i % 10) - Decimal(5)
            open_ = base + drift
            close = open_ + (Decimal(1) if i % 2 == 0 else Decimal(-1))
            high = max(open_, close) + Decimal(1)
            low = min(open_, close) - Decimal(1)
            bars.append(
                Bar(
                    instrument=instrument,
                    ts=ts,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=Decimal(1000 + i),
                )
            )
            ts += step
            i += 1
        return bars

    async def option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> OptionChain:
        exp = expiry or (datetime.now(UTC).date() + timedelta(days=30))
        spot = _seed_price(underlying)
        contracts: list[OptionContract] = []
        for offset in (Decimal(-10), Decimal(0), Decimal(10)):
            strike = spot + offset
            for opt_type in ("C", "P"):
                ins = Instrument(
                    symbol=underlying,
                    asset_class=AssetClass.OPTION,
                    expiry=exp,
                    strike=strike,
                    option_type=opt_type,
                    multiplier=Decimal(100),
                )
                mid = Decimal(5) + (abs(offset) / Decimal(10))
                contracts.append(
                    OptionContract(
                        instrument=ins,
                        bid=mid - Decimal("0.05"),
                        ask=mid + Decimal("0.05"),
                        last=mid,
                        implied_volatility=Decimal("0.25"),
                        delta=Decimal("0.5"),
                    )
                )
        return OptionChain(underlying=underlying, contracts=contracts)

    async def stream(self, instruments: list[Instrument]) -> AsyncIterator[Quote]:
        for ins in instruments:
            yield await self.quote(ins)

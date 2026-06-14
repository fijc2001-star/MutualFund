"""Provider contract suite, run against the FakeProvider (reusable for any provider)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.marketdata.providers.fake import FakeProvider
from mutualfund.marketdata.types import TimeFrame


async def test_quote_spread_and_mid() -> None:
    provider = FakeProvider()
    q = await provider.quote(Instrument("AAPL", AssetClass.EQUITY))
    assert q.ask > q.bid
    assert q.mid == (q.bid + q.ask) / Decimal(2)


async def test_bars_are_well_formed() -> None:
    provider = FakeProvider()
    end = datetime.now(UTC)
    start = end - timedelta(days=5)
    bars = await provider.bars(
        Instrument("AAPL", AssetClass.EQUITY), TimeFrame.D1, start, end
    )
    assert len(bars) >= 5
    assert all(b.high >= b.low for b in bars)


async def test_option_chain_shape() -> None:
    provider = FakeProvider()
    chain = await provider.option_chain("AAPL")
    assert chain.underlying == "AAPL"
    assert len(chain.contracts) == 6
    assert all(c.instrument.asset_class is AssetClass.OPTION for c in chain.contracts)


async def test_stream_yields_quotes() -> None:
    provider = FakeProvider()
    quotes = [q async for q in provider.stream([Instrument("AAPL", AssetClass.EQUITY)])]
    assert len(quotes) == 1

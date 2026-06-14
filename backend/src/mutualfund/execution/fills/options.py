"""OptionsPricingModel — option fill price + mark-to-market between fills.

v1 sources both from the market snapshot quotes. Black-Scholes (from underlying + IV)
is a pluggable alternative later (REQUIREMENTS §5.5.1).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from ...foundation.instrument import Instrument
from ..orders import MarketSnapshot, Side


class OptionsPricingModel(Protocol):
    def fill_price(
        self, instrument: Instrument, snapshot: MarketSnapshot, side: Side
    ) -> Decimal: ...

    def mark(self, instrument: Instrument, snapshot: MarketSnapshot) -> Decimal: ...


class QuoteOptionsPricing:
    """Cross-the-spread fills; mark at last price."""

    def fill_price(
        self, instrument: Instrument, snapshot: MarketSnapshot, side: Side
    ) -> Decimal:
        quote = snapshot.quote(instrument)
        return quote.ask if side is Side.BUY else quote.bid

    def mark(self, instrument: Instrument, snapshot: MarketSnapshot) -> Decimal:
        return snapshot.quote(instrument).last

"""FillPriceModel — what price an equity order fills at. Default: cross-the-spread."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from ..orders import MarketSnapshot, Order, Side


class FillPriceModel(Protocol):
    def price(self, order: Order, snapshot: MarketSnapshot) -> Decimal: ...


class CrossSpreadFill:
    """Buy at the ask, sell at the bid — conservative (you pay the spread)."""

    def price(self, order: Order, snapshot: MarketSnapshot) -> Decimal:
        quote = snapshot.quote(order.instrument)
        return quote.ask if order.side is Side.BUY else quote.bid

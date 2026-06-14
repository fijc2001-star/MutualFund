"""SlippageModel — adverse price movement beyond the quote. Default: fixed bps."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from ..orders import Order, Side


class SlippageModel(Protocol):
    def adjust(self, price: Decimal, order: Order) -> Decimal: ...


class FixedBpsSlippage:
    """Move the fill price adversely by a fixed number of basis points."""

    def __init__(self, bps: Decimal = Decimal(5)) -> None:
        self._factor = bps / Decimal(10_000)

    def adjust(self, price: Decimal, order: Order) -> Decimal:
        if order.side is Side.BUY:
            return price * (Decimal(1) + self._factor)
        return price * (Decimal(1) - self._factor)

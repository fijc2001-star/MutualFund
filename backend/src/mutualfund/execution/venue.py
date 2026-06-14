"""The ExecutionVenue interface — sandbox now, live broker later (same signal path)."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from .orders import Fill, MarketSnapshot, Order, Position


class ExecutionVenue(Protocol):
    async def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill: ...

    def positions(self) -> list[Position]: ...

    def cash(self) -> Decimal: ...

    def equity(self, snapshot: MarketSnapshot) -> Decimal: ...

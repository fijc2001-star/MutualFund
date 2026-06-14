"""Execution domain types: orders, fills, positions, and a market snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from ..foundation.instrument import Instrument
from ..marketdata.types import Quote


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"  # v1: market only


@dataclass(frozen=True, slots=True)
class Order:
    instrument: Instrument
    side: Side
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET


@dataclass(frozen=True, slots=True)
class Fill:
    instrument: Instrument
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    ts: datetime


@dataclass(slots=True)
class Position:
    instrument: Instrument
    quantity: Decimal
    avg_price: Decimal


class MissingQuoteError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Quotes for the instruments being traded/marked, keyed by Instrument.key."""

    quotes: dict[str, Quote]

    def quote(self, instrument: Instrument) -> Quote:
        try:
            return self.quotes[instrument.key]
        except KeyError as exc:
            raise MissingQuoteError(f"No quote for {instrument.key}") from exc

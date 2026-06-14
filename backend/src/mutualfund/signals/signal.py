"""Signal value types: what a strategy emits, with an explainable rationale.

A `Signal` is *directional* (BUY/SELL/CLOSE) and carries a `strength` in [0, 1]; turning
strength into an order quantity is M6's job (sizing). The `Rationale` is streamed to the
chart and stored so a trade can always be explained (REQUIREMENTS §5.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from ..foundation.instrument import Instrument


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"  # flatten the current position (direction inferred at execution)


@dataclass(frozen=True, slots=True)
class Rationale:
    """Why a signal fired — thesis, the indicators that triggered it, and what voids it."""

    thesis: str
    indicators: list[str] = field(default_factory=list)
    invalidation: str | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    instrument: Instrument
    action: Action
    strength: Decimal = Decimal(1)  # conviction in [0, 1]; sized into an order by M6
    rationale: Rationale | None = None

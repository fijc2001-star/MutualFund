"""Position sizing: turn a `Signal` into an order quantity.

Entries are sized by the chosen model and scaled by the signal's conviction (`strength`);
exits flatten the current position (v1 is long-only, so a SELL/CLOSE sells what's held).
Quantities are floored to whole units — shares/contracts, never fractional.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from math import sqrt
from statistics import fmean
from typing import Protocol, runtime_checkable

from ..foundation.instrument import Instrument
from ..signals.signal import Action, Signal


@dataclass(frozen=True, slots=True)
class SizingContext:
    """What a sizer needs: the entry reference price, account equity, current position,
    and recent closes (for volatility-based sizing)."""

    instrument: Instrument
    price: Decimal
    equity: Decimal
    position: Decimal = Decimal(0)
    closes: Sequence[float] = ()


@runtime_checkable
class PositionSizer(Protocol):
    def quantity(self, signal: Signal, ctx: SizingContext) -> Decimal: ...


def _floor_units(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_DOWN) if value > 0 else Decimal(0)


def _realized_vol(closes: Sequence[float], lookback: int) -> float | None:
    """Sample stdev of simple returns over the last `lookback` bars; None if too few."""
    window = list(closes[-(lookback + 1) :])
    rets = [
        window[i] / window[i - 1] - 1.0
        for i in range(1, len(window))
        if window[i - 1] != 0
    ]
    if len(rets) < 2:
        return None
    mean = fmean(rets)
    return sqrt(fmean([(r - mean) ** 2 for r in rets]))


class _EntrySizer(ABC):
    """Shared exit semantics; subclasses supply only the entry quantity."""

    def quantity(self, signal: Signal, ctx: SizingContext) -> Decimal:
        if signal.action in (Action.SELL, Action.CLOSE):
            return abs(ctx.position)  # flatten (long-only v1)
        return _floor_units(self._entry_quantity(ctx) * signal.strength)

    @abstractmethod
    def _entry_quantity(self, ctx: SizingContext) -> Decimal: ...


class FixedQuantity(_EntrySizer):
    """Always enter a fixed number of units."""

    def __init__(self, quantity: Decimal) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._quantity = quantity

    def _entry_quantity(self, ctx: SizingContext) -> Decimal:
        return self._quantity


class FixedFractional(_EntrySizer):
    """Allocate a fixed fraction of equity to the position."""

    def __init__(self, fraction: Decimal) -> None:
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be in (0, 1]")
        self._fraction = fraction

    def _entry_quantity(self, ctx: SizingContext) -> Decimal:
        notional_per_unit = ctx.price * ctx.instrument.multiplier
        if notional_per_unit <= 0:
            return Decimal(0)
        return ctx.equity * self._fraction / notional_per_unit


class VolatilityTarget(_EntrySizer):
    """Size so the position's return volatility ~ `target_vol`, capped at `max_fraction`
    of equity. Falls back to the cap when volatility can't be estimated."""

    def __init__(
        self,
        target_vol: Decimal,
        *,
        lookback: int = 20,
        max_fraction: Decimal = Decimal("0.25"),
    ) -> None:
        if target_vol <= 0:
            raise ValueError("target_vol must be positive")
        if not 0 < max_fraction <= 1:
            raise ValueError("max_fraction must be in (0, 1]")
        self._target = target_vol
        self._lookback = lookback
        self._max_fraction = max_fraction

    def _entry_quantity(self, ctx: SizingContext) -> Decimal:
        notional_per_unit = ctx.price * ctx.instrument.multiplier
        if notional_per_unit <= 0:
            return Decimal(0)
        cap_value = ctx.equity * self._max_fraction
        vol = _realized_vol(ctx.closes, self._lookback)
        if vol is None or vol <= 0:
            target_value = cap_value
        else:
            target_value = min(cap_value, ctx.equity * self._target / Decimal(str(vol)))
        return target_value / notional_per_unit

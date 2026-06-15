"""Deterministic-ish fake market + signal generator for the visualization prototype.

Produces a random-walk candle series and emits BUY/SELL signals on simple momentum
flips. Seeded RNG keeps it testable.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class DemoBar:
    time: int  # unix seconds (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class DemoSignal:
    time: int
    side: str  # "buy" | "sell"
    price: float
    reason: str


class DemoFeed:
    """Generates a live-looking candle stream and momentum-based signals."""

    def __init__(
        self,
        symbol: str,
        *,
        start_time: int = 1_700_000_000,
        step_seconds: int = 60,
        start_price: float = 100.0,
        seed: int | None = None,
    ) -> None:
        self.symbol = symbol
        self._t = start_time
        self._step = step_seconds
        self._price = start_price
        self._rng = random.Random(seed if seed is not None else hash(symbol) & 0xFFFF)
        self._closes: list[float] = []
        self._since_signal = 0

    def _next_close(self) -> float:
        drift = self._rng.uniform(-1.5, 1.5)
        self._price = max(1.0, self._price + drift)
        return round(self._price, 2)

    def next_bar(self) -> DemoBar:
        open_ = round(self._price, 2)
        close = self._next_close()
        high = round(max(open_, close) + self._rng.uniform(0, 1.0), 2)
        low = round(min(open_, close) - self._rng.uniform(0, 1.0), 2)
        # Volume loosely scales with the bar's range, so VWAP/volume tools look alive.
        volume = round(800 + abs(close - open_) * 600 + self._rng.uniform(0, 1500))
        bar = DemoBar(time=self._t, open=open_, high=high, low=low, close=close, volume=volume)
        self._t += self._step
        self._closes.append(close)
        self._since_signal += 1
        return bar

    def maybe_signal(self, bar: DemoBar) -> DemoSignal | None:
        """Emit a signal on a momentum flip, throttled so the chart isn't noisy."""
        if len(self._closes) < 4 or self._since_signal < 4:
            return None
        a, b, c = self._closes[-3], self._closes[-2], self._closes[-1]
        rising = c > b > a
        falling = c < b < a
        if rising:
            self._since_signal = 0
            return DemoSignal(bar.time, "buy", bar.close, "3-bar upward momentum")
        if falling:
            self._since_signal = 0
            return DemoSignal(bar.time, "sell", bar.close, "3-bar downward momentum")
        return None

    def snapshot(self, count: int = 60) -> list[DemoBar]:
        return [self.next_bar() for _ in range(count)]


def bar_dict(bar: DemoBar) -> dict[str, float | int]:
    return asdict(bar)


def signal_dict(signal: DemoSignal) -> dict[str, float | int | str]:
    return asdict(signal)

"""Drive the chart from the REAL M5 sandbox + M10 ledger.

A small SMA-crossover demo strategy generates orders; they execute through the real
`SandboxLedger` (writing fills to the hash-chained `EventLedger`), and we stream the
actual fills + live performance to the client. This replaces the fully-fake demo feed.

The built-in strategy is a placeholder until M3/M9 (Strategy/SignalEngine) land.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from ..execution.orders import MarketSnapshot, Order, Side
from ..execution.sandbox import SandboxLedger
from ..foundation.clock import SystemClock
from ..foundation.ids import new_id
from ..foundation.instrument import AssetClass, Instrument
from ..foundation.uow import UnitOfWork
from ..ledger.ledger import EventLedger
from ..ledger.performance import PerformanceCalculator
from ..marketdata.types import Quote
from .demo import DemoFeed, bar_dict

Send = Callable[[dict[str, Any]], Awaitable[None]]

_SHORT = 9
_LONG = 21
_QTY = Decimal(100)
_SPREAD = Decimal("0.02")


def _sma(values: list[float], n: int) -> float | None:
    return sum(values[-n:]) / n if len(values) >= n else None


class SmaCross:
    """Emits 'buy'/'sell' when the short SMA crosses the long SMA."""

    def __init__(self) -> None:
        self._above: bool | None = None

    def update(self, closes: list[float]) -> str | None:
        short, long = _sma(closes, _SHORT), _sma(closes, _LONG)
        if short is None or long is None:
            return None
        above = short > long
        signal: str | None = None
        if self._above is not None and above != self._above:
            signal = "buy" if above else "sell"
        self._above = above
        return signal


class SandboxSession:
    """Runs one live (symbol, sandbox) session, streaming bars/fills/perf via `send`."""

    def __init__(self, uow: UnitOfWork, symbol: str, starting_cash: Decimal) -> None:
        self._uow = uow
        self._symbol = symbol
        self._instrument = Instrument(symbol, AssetClass.EQUITY)
        self._stream_id = f"sandbox:{symbol}:{new_id()}"
        self._starting_cash = starting_cash
        self._feed = DemoFeed(symbol)
        self._strategy = SmaCross()
        self._closes: list[float] = []
        self._clock = SystemClock()
        self._ledger = EventLedger(uow.session, self._clock)
        self._sandbox = SandboxLedger(
            self._ledger, self._stream_id, starting_cash=starting_cash, clock=self._clock
        )
        self._calc = PerformanceCalculator()
        self._long = False  # currently holding a long position?

    def _snapshot_for(self, close: float) -> MarketSnapshot:
        c = Decimal(str(close))
        quote = Quote(
            self._instrument, c - _SPREAD, c + _SPREAD, c, self._clock.now()
        )
        return MarketSnapshot({self._instrument.key: quote})

    async def run(self, send: Send, *, interval: float, max_ticks: int | None = None) -> None:
        history = self._feed.snapshot(60)
        self._closes = [b.close for b in history]
        await send(
            {
                "type": "snapshot",
                "symbol": self._symbol,
                "bars": [bar_dict(b) for b in history],
            }
        )

        tick = 0
        while max_ticks is None or tick < max_ticks:
            if interval > 0:
                await asyncio.sleep(interval)
            tick += 1

            bar = self._feed.next_bar()
            self._closes.append(bar.close)
            await send({"type": "bar", "bar": bar_dict(bar)})

            snap = self._snapshot_for(bar.close)
            action = self._strategy.update(self._closes)
            if action == "buy" and not self._long:
                fill = await self._sandbox.submit(
                    Order(self._instrument, Side.BUY, _QTY), snap
                )
                self._long = True
                await send(self._signal_msg(bar.time, "buy", fill.price, "SMA cross up"))
            elif action == "sell" and self._long:
                fill = await self._sandbox.submit(
                    Order(self._instrument, Side.SELL, _QTY), snap
                )
                self._long = False
                await send(self._signal_msg(bar.time, "sell", fill.price, "SMA cross down"))

            await self._sandbox.mark_to_market(snap)
            await send(await self._perf_msg(snap))
            await self._uow.commit()

    def _signal_msg(
        self, time: int, side: str, price: Decimal, reason: str
    ) -> dict[str, Any]:
        return {
            "type": "signal",
            "signal": {"time": time, "side": side, "price": float(price), "reason": reason},
        }

    async def _perf_msg(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        events = await self._ledger.replay(self._stream_id)
        rec = self._calc.from_events(events, self._starting_cash)
        positions = self._sandbox.positions()
        qty = positions[0].quantity if positions else Decimal(0)
        return {
            "type": "perf",
            "perf": {
                "equity": float(self._sandbox.equity(snapshot)),
                "cash": float(self._sandbox.cash()),
                "position": float(qty),
                "net_pnl": float(rec.net_pnl),
                "return_pct": float(rec.return_pct),
                "max_drawdown_pct": float(rec.max_drawdown_pct),
                "num_trades": rec.num_trades,
            },
        }

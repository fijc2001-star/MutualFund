"""Drive the chart from the REAL M5 sandbox + M10 ledger, running a REAL bot.

A stored-style `BotDefinition` (SMA-cross) is evaluated each tick by the `SignalEngine`
(M3/M9); the resulting signals are sized into orders and executed through the real
`SandboxLedger` (writing fills to the hash-chained `EventLedger`). We stream the actual
fills, their rationale, and live performance to the client.

Position sizing here is a fixed quantity until M6 (PositionSizer + RiskModel) lands.
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
from ..signals.engine import SignalEngine
from ..signals.signal import Action, Signal
from ..strategy.strategy import BotDefinition, StrategyContext
from .demo import DemoFeed, bar_dict

Send = Callable[[dict[str, Any]], Awaitable[None]]

_SHORT = 9
_LONG = 21
_QTY = Decimal(100)
_SPREAD = Decimal("0.02")


class SandboxSession:
    """Runs one live (symbol, sandbox) session, streaming bars/fills/perf via `send`."""

    def __init__(self, uow: UnitOfWork, symbol: str, starting_cash: Decimal) -> None:
        self._uow = uow
        self._symbol = symbol
        self._instrument = Instrument(symbol, AssetClass.EQUITY)
        self._stream_id = f"sandbox:{symbol}:{new_id()}"
        self._starting_cash = starting_cash
        self._feed = DemoFeed(symbol)
        self._engine = SignalEngine()
        self._definition = BotDefinition(
            strategy_id="sma_cross", params={"fast": _SHORT, "slow": _LONG}
        )
        self._closes: list[float] = []
        self._clock = SystemClock()
        self._ledger = EventLedger(uow.session, self._clock)
        self._sandbox = SandboxLedger(
            self._ledger, self._stream_id, starting_cash=starting_cash, clock=self._clock
        )
        self._calc = PerformanceCalculator()

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
            ctx = StrategyContext(self._instrument, self._closes, position=self._position())
            for signal in self._engine.run(self._definition, ctx):
                await self._execute(signal, snap, bar.time, send)

            await self._sandbox.mark_to_market(snap)
            await send(await self._perf_msg(snap))
            await self._uow.commit()

    def _position(self) -> Decimal:
        positions = self._sandbox.positions()
        return positions[0].quantity if positions else Decimal(0)

    async def _execute(
        self, signal: Signal, snap: MarketSnapshot, time: int, send: Send
    ) -> None:
        """Size a signal into an order (fixed qty until M6) and execute it on the sandbox."""
        side = Side.BUY if signal.action is Action.BUY else Side.SELL
        fill = await self._sandbox.submit(Order(self._instrument, side, _QTY), snap)
        await send(self._signal_msg(time, side.value, fill.price, signal))

    def _signal_msg(
        self, time: int, side: str, price: Decimal, signal: Signal
    ) -> dict[str, Any]:
        rationale = signal.rationale
        return {
            "type": "signal",
            "signal": {
                "time": time,
                "side": side,
                "price": float(price),
                "reason": rationale.thesis if rationale else side,
                "rationale": {
                    "thesis": rationale.thesis,
                    "indicators": rationale.indicators,
                    "invalidation": rationale.invalidation,
                }
                if rationale
                else None,
            },
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

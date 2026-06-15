"""Drive the chart from the REAL M5 sandbox + M10 ledger, running a REAL, persisted bot.

This is Phase 3's full integrated flow end to end: a persisted `BotVersion` (SMA-cross) in
EVALUATION is run each tick by the `SignalEngine` (M3/M9); each signal is sized (M6
`PositionSizer`), checked against portfolio limits (`RiskModel`) and hard account guardrails
(`GuardrailPolicy`), and only then executed through the real `SandboxLedger` (writing fills
to the hash-chained `EventLedger`). When the session ends, the `PerformanceCalculator` (M10)
replays the ledger and the `QualificationService` (M4) gates the bot's lifecycle — promoting
it to LISTED or delisting it. Fills, rationale, live performance, blocks, and lifecycle state
are all streamed to the client.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from ..config import get_settings
from ..execution.orders import MarketSnapshot, Order, Side
from ..execution.sandbox import SandboxLedger
from ..foundation.audit import AuditLog
from ..foundation.clock import SystemClock
from ..foundation.ids import new_id
from ..foundation.instrument import AssetClass, Instrument
from ..foundation.uow import UnitOfWork
from ..ledger.ledger import EventLedger
from ..ledger.performance import PerformanceCalculator
from ..lifecycle.lifecycle import BotLifecycle, BotState
from ..lifecycle.qualification import (
    PolicyResult,
    QualificationInput,
    QualificationPolicy,
    baseline_policy,
)
from ..lifecycle.service import QualificationService
from ..marketdata.types import Quote
from ..risk.guardrails import AccountRisk, GuardrailLimits, GuardrailPolicy
from ..risk.model import PortfolioState, RiskLimits, RiskModel
from ..risk.sizing import FixedFractional, PositionSizer, SizingContext
from ..signals.engine import SignalEngine
from ..signals.signal import Action, Signal
from ..strategy.models import BotRegistry, BotVersion
from ..strategy.strategy import StrategyContext
from .demo import DemoFeed, bar_dict

Send = Callable[[dict[str, Any]], Awaitable[None]]

_SECONDS_PER_DAY = 86_400
_SHORT = 9
_LONG = 21
_SPREAD = Decimal("0.02")
# ~10 days of 1-min history so day/week-based indicators (Key Levels, VWAP) have context.
_HISTORY_BARS = 14_400


class SandboxSession:
    """Runs one live (symbol, sandbox) session, streaming bars/fills/perf via `send`."""

    def __init__(
        self,
        uow: UnitOfWork,
        symbol: str,
        starting_cash: Decimal,
        *,
        sizer: PositionSizer | None = None,
        risk_model: RiskModel | None = None,
        guardrails: GuardrailPolicy | None = None,
        kill_switch: bool | None = None,
        policy: QualificationPolicy | None = None,
    ) -> None:
        self._uow = uow
        self._symbol = symbol
        self._instrument = Instrument(symbol, AssetClass.EQUITY)
        self._stream_id = f"sandbox:{symbol}:{new_id()}"
        self._starting_cash = starting_cash
        self._feed = DemoFeed(symbol)
        self._engine = SignalEngine()
        self._closes: list[float] = []
        self._clock = SystemClock()
        self._ledger = EventLedger(uow.session, self._clock)
        self._sandbox = SandboxLedger(
            self._ledger, self._stream_id, starting_cash=starting_cash, clock=self._clock
        )
        self._calc = PerformanceCalculator()
        self._audit = AuditLog(uow.session, self._clock)

        # M3/M4 — a persisted bot we run and then qualify (created in run()).
        self._bots = BotRegistry(uow.session, clock=self._clock)
        self._lifecycle = BotLifecycle(uow.session, clock=self._clock)
        self._qualification = QualificationService(
            uow.session, policy=policy or baseline_policy(), lifecycle=self._lifecycle,
            clock=self._clock,
        )
        self._version: BotVersion | None = None
        self._first_time: int | None = None
        self._last_time: int | None = None

        settings = get_settings()
        self._sizer = sizer or FixedFractional(settings.risk_sizing_fraction)
        self._risk = risk_model or RiskModel(
            RiskLimits(
                max_position_pct=settings.risk_max_position_pct,
                max_options_leverage=settings.risk_max_options_leverage,
            )
        )
        self._guardrails = guardrails or GuardrailPolicy(
            GuardrailLimits(
                daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
                max_drawdown_pct=settings.risk_max_drawdown_pct,
            )
        )
        self._kill_switch = (
            settings.risk_kill_switch if kill_switch is None else kill_switch
        )
        self._day_start_equity = starting_cash
        self._peak_equity = starting_cash

    def _snapshot_for(self, close: float) -> MarketSnapshot:
        c = Decimal(str(close))
        quote = Quote(
            self._instrument, c - _SPREAD, c + _SPREAD, c, self._clock.now()
        )
        return MarketSnapshot({self._instrument.key: quote})

    async def run(self, send: Send, *, interval: float, max_ticks: int | None = None) -> None:
        history = self._feed.snapshot(_HISTORY_BARS)
        self._closes = [b.close for b in history]
        await send(
            {
                "type": "snapshot",
                "symbol": self._symbol,
                "bars": [bar_dict(b) for b in history],
            }
        )

        version = await self._start_evaluation()
        await send(self._lifecycle_msg())

        tick = 0
        while max_ticks is None or tick < max_ticks:
            if interval > 0:
                await asyncio.sleep(interval)
            tick += 1

            bar = self._feed.next_bar()
            self._closes.append(bar.close)
            if self._first_time is None:
                self._first_time = bar.time
            self._last_time = bar.time
            await send({"type": "bar", "bar": bar_dict(bar)})

            snap = self._snapshot_for(bar.close)
            equity = self._sandbox.equity(snap)
            self._peak_equity = max(self._peak_equity, equity)

            ctx = StrategyContext(self._instrument, self._closes, position=self._position())
            signals = self._engine.run(version.definition, ctx)
            if signals:
                guard = self._guardrails.enforce(
                    AccountRisk(
                        equity=equity,
                        day_start_equity=self._day_start_equity,
                        peak_equity=self._peak_equity,
                        kill_switch=self._kill_switch,
                    )
                )
                for signal in signals:
                    if guard.halted:
                        await self._block(signal, bar.time, send, "guardrail", guard.reason)
                    else:
                        await self._handle(signal, snap, equity, bar.time, send)

            await self._sandbox.mark_to_market(snap)
            await send(await self._perf_msg(snap))
            await self._uow.commit()

        # End of run: replay the ledger into a PerformanceRecord and gate the lifecycle.
        result = await self._qualify()
        await send(self._lifecycle_msg(result))
        await self._uow.commit()

    async def _start_evaluation(self) -> BotVersion:
        """Create the persisted bot, publish its version, and move it into EVALUATION."""
        bot = await self._bots.create_bot(name=f"SMA demo {self._symbol}", owner_id="demo")
        version = await self._bots.publish(
            bot,
            strategy_id="sma_cross",
            params={"fast": _SHORT, "slow": _LONG},
            universe=[self._symbol],
        )
        await self._lifecycle.transition(
            version, BotState.EVALUATION, reason="sandbox evaluation started"
        )
        self._version = version
        return version

    async def _qualify(self) -> PolicyResult:
        events = await self._ledger.replay(self._stream_id)
        record = self._calc.from_events(events, self._starting_cash)
        assert self._version is not None
        return await self._qualification.evaluate(
            self._version, QualificationInput(record, evaluation_days=self._eval_days())
        )

    def _eval_days(self) -> int:
        if self._first_time is None or self._last_time is None:
            return 0
        return (self._last_time - self._first_time) // _SECONDS_PER_DAY

    def _lifecycle_msg(self, result: PolicyResult | None = None) -> dict[str, Any]:
        assert self._version is not None
        lifecycle: dict[str, Any] = {
            "bot_id": self._version.bot_id,
            "version": self._version.version,
            "state": self._version.state,
        }
        if result is not None:
            lifecycle["qualification"] = {
                "policy": result.policy_name,
                "policy_version": result.policy_version,
                "passed": result.passed,
                "failures": [c.name for c in result.failures],
            }
        return {"type": "lifecycle", "lifecycle": lifecycle}

    def _position(self) -> Decimal:
        positions = self._sandbox.positions()
        return positions[0].quantity if positions else Decimal(0)

    async def _handle(
        self, signal: Signal, snap: MarketSnapshot, equity: Decimal, time: int, send: Send
    ) -> None:
        """signal → PositionSizer → Order → RiskModel.check → (if approved) sandbox.submit."""
        price = snap.quote(self._instrument).mid
        position = self._position()
        qty = self._sizer.quantity(
            signal,
            SizingContext(self._instrument, price, equity, position, self._closes),
        )
        if qty <= 0:
            return

        side = Side.BUY if signal.action is Action.BUY else Side.SELL
        order = Order(self._instrument, side, qty)
        portfolio = PortfolioState(
            equity=equity,
            positions=self._sandbox.positions(),
            marks={self._instrument.key: price},
        )
        decision = self._risk.check(order, portfolio)
        if not decision.approved:
            await self._block(signal, time, send, "risk", decision.reason)
            return

        fill = await self._sandbox.submit(order, snap)
        await send(self._signal_msg(time, side.value, fill.price, signal))

    async def _block(
        self, signal: Signal, time: int, send: Send, kind: str, reason: str | None
    ) -> None:
        """Audit a rejected order and surface it to the client — never silently dropped."""
        await self._audit.record(
            "order_blocked",
            actor=self._stream_id,
            payload={
                "kind": kind,
                "reason": reason,
                "symbol": self._symbol,
                "action": signal.action.value,
            },
        )
        await send(
            {
                "type": "blocked",
                "blocked": {
                    "time": time,
                    "kind": kind,
                    "reason": reason,
                    "action": signal.action.value,
                },
            }
        )

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

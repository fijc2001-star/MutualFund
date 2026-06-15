"""BacktestService — run a bot over its deterministic history and measure performance.

Drives the same components as the live sandbox session (engine → PositionSizer → RiskModel /
GuardrailPolicy → SandboxLedger), but over the *whole* history rather than only live ticks,
then derives a PerformanceRecord (M10) + an equity curve. Fills are written to a throwaway
ledger stream that the caller rolls back, so a backtest leaves no trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..execution.orders import MarketSnapshot, Order, Side
from ..execution.sandbox import SandboxLedger
from ..foundation.clock import Clock, SystemClock
from ..foundation.ids import new_id
from ..foundation.instrument import AssetClass, Instrument
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.ledger import EventLedger
from ..ledger.performance import PerformanceCalculator
from ..marketdata.types import Quote
from ..realtime.demo import DemoFeed
from ..risk.guardrails import AccountRisk, GuardrailLimits, GuardrailPolicy
from ..risk.model import PortfolioState, RiskLimits, RiskModel
from ..risk.sizing import FixedFractional, SizingContext
from ..signals.engine import SignalEngine
from ..signals.signal import Action, Signal
from ..strategy.strategy import BotDefinition, StrategyContext

_DEFAULT_HISTORY_BARS = 14_400
_SHORT = 9
_LONG = 21
_SPREAD = Decimal("0.02")
_EQUITY_POINTS = 500  # downsample the curve to keep the payload small


@dataclass(frozen=True, slots=True)
class BacktestResult:
    perf: dict[str, Any]
    equity: list[dict[str, Any]]  # [{ "time": unix_s, "value": equity }]


class BacktestService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        history_bars: int = _DEFAULT_HISTORY_BARS,
        clock: Clock | None = None,
    ) -> None:
        self._session = session
        self._clock = clock or SystemClock()
        self._history = history_bars
        self._engine = SignalEngine()
        self._calc = PerformanceCalculator()

        settings = get_settings()
        self._cash = settings.sandbox_starting_cash
        self._sizer = FixedFractional(settings.risk_sizing_fraction)
        self._risk = RiskModel(
            RiskLimits(
                max_position_pct=settings.risk_max_position_pct,
                max_options_leverage=settings.risk_max_options_leverage,
            )
        )
        self._guardrails = GuardrailPolicy(
            GuardrailLimits(
                daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
                max_drawdown_pct=settings.risk_max_drawdown_pct,
            )
        )
        self._kill_switch = settings.risk_kill_switch

    async def run(self, symbol: str, *, strategy_id: str = "sma_cross") -> BacktestResult:
        bars = DemoFeed(symbol).snapshot(self._history)
        instrument = Instrument(symbol, AssetClass.EQUITY)
        stream = f"backtest:{symbol}:{new_id()}"
        ledger = EventLedger(self._session, self._clock)
        sandbox = SandboxLedger(ledger, stream, starting_cash=self._cash, clock=self._clock)
        definition = BotDefinition(strategy_id, {"fast": _SHORT, "slow": _LONG})

        closes: list[float] = []
        equity_curve: list[tuple[int, Decimal]] = []
        peak = self._cash
        sample = max(1, len(bars) // _EQUITY_POINTS)
        last = len(bars) - 1

        for i, bar in enumerate(bars):
            closes.append(bar.close)
            snap = self._snapshot(instrument, bar.close)
            equity = sandbox.equity(snap)
            peak = max(peak, equity)

            ctx = StrategyContext(instrument, closes, position=self._position(sandbox))
            signals = self._engine.run(definition, ctx)
            if signals:
                guard = self._guardrails.enforce(
                    AccountRisk(
                        equity=equity,
                        day_start_equity=self._cash,
                        peak_equity=peak,
                        kill_switch=self._kill_switch,
                    )
                )
                if not guard.halted:
                    for sig in signals:
                        await self._execute(sandbox, instrument, sig, snap, equity)

            if i % sample == 0 or i == last:
                equity_curve.append((bar.time, sandbox.equity(snap)))

        return await self._result(ledger, stream, sandbox, equity_curve)

    async def _execute(
        self,
        sandbox: SandboxLedger,
        instrument: Instrument,
        signal: Signal,
        snap: MarketSnapshot,
        equity: Decimal,
    ) -> None:
        price = snap.quote(instrument).mid
        position = self._position(sandbox)
        qty = self._sizer.quantity(signal, SizingContext(instrument, price, equity, position))
        if qty <= 0:
            return
        side = Side.BUY if signal.action is Action.BUY else Side.SELL
        order = Order(instrument, side, qty)
        portfolio = PortfolioState(equity, sandbox.positions(), {instrument.key: price})
        if not self._risk.check(order, portfolio).approved:
            return
        await sandbox.submit(order, snap)

    async def _result(
        self,
        ledger: EventLedger,
        stream: str,
        sandbox: SandboxLedger,
        equity_curve: list[tuple[int, Decimal]],
    ) -> BacktestResult:
        fills = await ledger.replay(stream)  # FILL events flushed during the run
        marks = [
            LedgerEvent(
                stream_id=stream,
                event_type=LedgerEventType.MARK,
                payload={"equity": str(eq)},
                ts=datetime.fromtimestamp(ts, UTC),
            )
            for ts, eq in equity_curve
        ]
        rec = self._calc.from_events([*fills, *marks], self._cash)
        positions = sandbox.positions()
        position = positions[0].quantity if positions else Decimal(0)
        last_equity = equity_curve[-1][1] if equity_curve else self._cash
        perf = {
            "equity": float(last_equity),
            "cash": float(sandbox.cash()),
            "position": float(position),
            "net_pnl": float(rec.net_pnl),
            "return_pct": float(rec.return_pct),
            "max_drawdown_pct": float(rec.max_drawdown_pct),
            "num_trades": rec.num_trades,
            "win_rate": float(rec.win_rate),
            "sharpe": float(rec.sharpe) if rec.sharpe is not None else None,
        }
        return BacktestResult(
            perf=perf,
            equity=[{"time": ts, "value": float(eq)} for ts, eq in equity_curve],
        )

    def _snapshot(self, instrument: Instrument, close: float) -> MarketSnapshot:
        c = Decimal(str(close))
        quote = Quote(instrument, c - _SPREAD, c + _SPREAD, c, self._clock.now())
        return MarketSnapshot({instrument.key: quote})

    @staticmethod
    def _position(sandbox: SandboxLedger) -> Decimal:
        positions = sandbox.positions()
        return positions[0].quantity if positions else Decimal(0)

"""BacktestService — backtest a bot over a chosen [start, end] window through the live pipeline.

Indicators are warmed up on bars *before* the window; the bot starts flat at `start` and only
executes + is measured within `[start, end]`. Drives the same components as the live sandbox
(engine → PositionSizer → RiskModel / GuardrailPolicy → SandboxLedger) and derives a
PerformanceRecord (M10) + a per-bar equity curve. Fills go to a throwaway ledger stream the
caller rolls back, so a backtest leaves no trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..execution.orders import Fill, MarketSnapshot, Order, Side
from ..execution.sandbox import SandboxLedger
from ..foundation.clock import Clock, SystemClock
from ..foundation.ids import new_id
from ..foundation.instrument import AssetClass, Instrument
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.ledger import EventLedger
from ..ledger.performance import PerformanceCalculator
from ..marketdata.types import Quote
from ..realtime.demo import DemoFeed, bar_dict
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


@dataclass(frozen=True, slots=True)
class BacktestResult:
    start: int
    end: int
    bars: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    equity: list[dict[str, Any]]  # one { "time", "value" } per window bar, aligned with bars
    perf: dict[str, Any]


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

    async def run(
        self,
        symbol: str,
        *,
        strategy_id: str = "sma_cross",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> BacktestResult:
        all_bars = DemoFeed(symbol).snapshot(self._history)
        first, last = all_bars[0].time, all_bars[-1].time
        start = first if start_ts is None else max(first, min(start_ts, last))
        end = last if end_ts is None else max(start, min(end_ts, last))

        instrument = Instrument(symbol, AssetClass.EQUITY)
        stream = f"backtest:{symbol}:{new_id()}"
        ledger = EventLedger(self._session, self._clock)
        sandbox = SandboxLedger(ledger, stream, starting_cash=self._cash, clock=self._clock)
        definition = BotDefinition(strategy_id, {"fast": _SHORT, "slow": _LONG})

        closes: list[float] = []
        window_bars: list[dict[str, Any]] = []
        equity_pts: list[tuple[int, Decimal]] = []
        signals_out: list[dict[str, Any]] = []
        peak = self._cash

        for bar in all_bars:
            if bar.time > end:
                break
            closes.append(bar.close)  # warm up indicators across the whole prefix
            if bar.time < start:
                continue

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
                        fill = await self._execute(sandbox, instrument, sig, snap, equity)
                        if fill is not None:
                            signals_out.append(self._signal_dict(bar.time, sig, fill.price))

            window_bars.append(bar_dict(bar))
            equity_pts.append((bar.time, sandbox.equity(snap)))

        return await self._result(ledger, stream, start, end, window_bars, signals_out, equity_pts)

    async def _execute(
        self,
        sandbox: SandboxLedger,
        instrument: Instrument,
        signal: Signal,
        snap: MarketSnapshot,
        equity: Decimal,
    ) -> Fill | None:
        price = snap.quote(instrument).mid
        position = self._position(sandbox)
        qty = self._sizer.quantity(signal, SizingContext(instrument, price, equity, position))
        if qty <= 0:
            return None
        side = Side.BUY if signal.action is Action.BUY else Side.SELL
        order = Order(instrument, side, qty)
        portfolio = PortfolioState(equity, sandbox.positions(), {instrument.key: price})
        if not self._risk.check(order, portfolio).approved:
            return None
        return await sandbox.submit(order, snap)

    async def _result(
        self,
        ledger: EventLedger,
        stream: str,
        start: int,
        end: int,
        window_bars: list[dict[str, Any]],
        signals_out: list[dict[str, Any]],
        equity_pts: list[tuple[int, Decimal]],
    ) -> BacktestResult:
        fills = await ledger.replay(stream)
        marks = [
            LedgerEvent(
                stream_id=stream,
                event_type=LedgerEventType.MARK,
                payload={"equity": str(eq)},
                ts=datetime.fromtimestamp(ts, UTC),
            )
            for ts, eq in equity_pts
        ]
        rec = self._calc.from_events([*fills, *marks], self._cash)
        last_equity = equity_pts[-1][1] if equity_pts else self._cash
        perf = {
            "equity": float(last_equity),
            "net_pnl": float(rec.net_pnl),
            "return_pct": float(rec.return_pct),
            "max_drawdown_pct": float(rec.max_drawdown_pct),
            "num_trades": rec.num_trades,
            "win_rate": float(rec.win_rate),
            "sharpe": float(rec.sharpe) if rec.sharpe is not None else None,
        }
        return BacktestResult(
            start=start,
            end=end,
            bars=window_bars,
            signals=signals_out,
            equity=[{"time": ts, "value": float(eq)} for ts, eq in equity_pts],
            perf=perf,
        )

    def _signal_dict(self, time: int, signal: Signal, price: Decimal) -> dict[str, Any]:
        rationale = signal.rationale
        side = "buy" if signal.action is Action.BUY else "sell"
        return {
            "time": time,
            "side": side,
            "price": float(price),
            "reason": rationale.thesis if rationale else side,
            "rationale": {
                "thesis": rationale.thesis if rationale else "",
                "indicators": rationale.indicators if rationale else [],
                "invalidation": rationale.invalidation if rationale else None,
            },
        }

    def _snapshot(self, instrument: Instrument, close: float) -> MarketSnapshot:
        c = Decimal(str(close))
        quote = Quote(instrument, c - _SPREAD, c + _SPREAD, c, self._clock.now())
        return MarketSnapshot({instrument.key: quote})

    @staticmethod
    def _position(sandbox: SandboxLedger) -> Decimal:
        positions = sandbox.positions()
        return positions[0].quantity if positions else Decimal(0)

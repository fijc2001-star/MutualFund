"""PortfolioService — combine several bots into one weighted capital allocation.

Each leg is backtested independently through the same pipeline (BacktestService) over the same
window; the legs share the demo feed's timestamps, so their per-bar equity curves align. The
portfolio curve is `capital × Σ wᵢ · (equityᵢ / starting_cash)` — i.e. capital split across the
bots by normalized weight — and portfolio stats come from that curve via the M10 calculator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..backtest.service import BacktestService
from ..config import get_settings
from ..foundation.clock import Clock
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.performance import PerformanceCalculator
from ..strategy.models import Bot, BotVersion

_DEFAULT_HISTORY_BARS = 14_400


@dataclass(frozen=True, slots=True)
class Allocation:
    bot: Bot
    version: BotVersion
    weight: float


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    capital: float
    equity: list[dict[str, Any]]
    perf: dict[str, Any]
    legs: list[dict[str, Any]]


class PortfolioService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        history_bars: int = _DEFAULT_HISTORY_BARS,
        clock: Clock | None = None,
    ) -> None:
        self._backtest = BacktestService(session, history_bars=history_bars, clock=clock)
        self._calc = PerformanceCalculator()
        self._cash = float(get_settings().sandbox_starting_cash)

    async def backtest(
        self,
        allocations: list[Allocation],
        *,
        capital: Decimal,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> PortfolioResult:
        total = sum(a.weight for a in allocations)
        n_alloc = len(allocations)
        weights = (
            [a.weight / total for a in allocations]
            if total > 0
            else [1.0 / n_alloc] * n_alloc
        )

        legs: list[dict[str, Any]] = []
        curves: list[list[tuple[int, float]]] = []
        for alloc, weight in zip(allocations, weights, strict=True):
            symbol = alloc.version.universe[0] if alloc.version.universe else "AAPL"
            res = await self._backtest.run(
                symbol,
                strategy_id=alloc.version.strategy_id,
                params=dict(alloc.version.params),
                start_ts=start_ts,
                end_ts=end_ts,
            )
            curves.append([(p["time"], p["value"]) for p in res.equity])
            legs.append(
                {
                    "bot_id": alloc.bot.id,
                    "name": alloc.bot.name,
                    "symbol": symbol,
                    "strategy_id": alloc.version.strategy_id,
                    "weight": round(weight, 4),
                    "perf": res.perf,
                }
            )

        cap = float(capital)
        n = min((len(c) for c in curves), default=0)
        equity: list[dict[str, Any]] = []
        for t in range(n):
            factor = sum(weights[i] * (curves[i][t][1] / self._cash) for i in range(len(curves)))
            equity.append({"time": curves[0][t][0], "value": cap * factor})

        num_trades = sum(int(leg["perf"]["num_trades"]) for leg in legs)
        return PortfolioResult(
            capital=cap, equity=equity, perf=self._perf(equity, capital, num_trades), legs=legs
        )

    def _perf(
        self, equity: list[dict[str, Any]], capital: Decimal, num_trades: int
    ) -> dict[str, Any]:
        marks = [
            LedgerEvent(
                stream_id="portfolio",
                event_type=LedgerEventType.MARK,
                payload={"equity": str(p["value"])},
                ts=datetime.fromtimestamp(p["time"], UTC),
            )
            for p in equity
        ]
        rec = self._calc.from_events(marks, capital)
        return {
            "equity": equity[-1]["value"] if equity else float(capital),
            "net_pnl": float(rec.net_pnl),
            "return_pct": float(rec.return_pct),
            "max_drawdown_pct": float(rec.max_drawdown_pct),
            "sharpe": float(rec.sharpe) if rec.sharpe is not None else None,
            "num_trades": num_trades,
        }

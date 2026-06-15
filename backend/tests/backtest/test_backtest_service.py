"""Backtesting a bot over its history yields trades, an equity curve, and summary stats."""

from __future__ import annotations

from mutualfund.backtest.service import BacktestService
from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork


async def test_backtest_produces_perf_and_equity_curve(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        result = await BacktestService(uow.session, history_bars=2000).run("AAPL")

        # Performance summary is well-formed.
        assert {
            "equity", "cash", "position", "net_pnl",
            "return_pct", "max_drawdown_pct", "num_trades", "win_rate", "sharpe",
        } <= result.perf.keys()
        assert result.perf["num_trades"] > 0  # the SMA bot traded over 2000 bars

        # Equity curve is sampled, time-ordered, and starts at/under the visible window.
        assert len(result.equity) > 1
        times = [p["time"] for p in result.equity]
        assert times == sorted(times)
        assert all(isinstance(p["value"], float) for p in result.equity)

        await uow.rollback()  # discard the throwaway backtest fills

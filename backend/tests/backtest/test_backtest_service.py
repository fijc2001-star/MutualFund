"""Backtesting yields per-bar bars/equity/signals + stats, and honors a [start, end] window."""

from __future__ import annotations

from mutualfund.backtest.service import BacktestService
from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork

_FIRST = 1_700_000_000  # DemoFeed default start_time
_STEP = 60


async def test_backtest_full_history(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        result = await BacktestService(uow.session, history_bars=2000).run("AAPL")

        assert {
            "equity", "net_pnl", "return_pct", "max_drawdown_pct",
            "num_trades", "win_rate", "sharpe",
        } <= result.perf.keys()
        assert result.perf["num_trades"] > 0

        # bars and equity are aligned 1:1 and time-ordered.
        assert len(result.bars) == len(result.equity) > 1
        times = [p["time"] for p in result.equity]
        assert times == sorted(times)

        # the M10 record + evaluation span are exposed for qualification (M-C)
        assert result.record.num_trades == result.perf["num_trades"]
        assert result.evaluation_days >= 1

        await uow.rollback()


async def test_backtest_runs_agent_strategy(tenant_ctx: TenantId) -> None:
    """The agentic strategy flows through the same pipeline (stub client, no API key needed)."""
    async with UnitOfWork() as uow:
        result = await BacktestService(uow.session, history_bars=2000).run(
            "AAPL", strategy_id="agent", params={"fast": 9, "slow": 21}
        )
        assert result.perf["num_trades"] > 0
        # Signals carry the agent's reasoning (RSI indicator + a thesis).
        assert result.signals
        rationale = result.signals[0]["rationale"]
        assert rationale["thesis"]
        assert any(ind.startswith("RSI(") for ind in rationale["indicators"])

        await uow.rollback()


async def test_backtest_window_is_bounded_and_warmed_up(tenant_ctx: TenantId) -> None:
    start = _FIRST + 500 * _STEP
    end = _FIRST + 1500 * _STEP
    async with UnitOfWork() as uow:
        result = await BacktestService(uow.session, history_bars=2000).run(
            "AAPL", start_ts=start, end_ts=end
        )

        assert result.start == start
        assert result.end == end
        # Every bar lies within the window...
        assert all(start <= b["time"] <= end for b in result.bars)
        assert len(result.bars) == 1001  # inclusive minute bars from start..end
        # ...and indicators were warmed up on the prefix, so it can still trade in-window.
        assert result.perf["num_trades"] > 0

        await uow.rollback()

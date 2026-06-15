"""A portfolio combines its legs' equity into one weighted curve + performance."""

from __future__ import annotations

from decimal import Decimal

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.portfolio.service import Allocation, PortfolioService
from mutualfund.strategy.models import BotRegistry


async def test_portfolio_combines_two_bots(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        reg = BotRegistry(uow.session)
        b1 = await reg.create_bot(name="AAPL bot", owner_id="owner-1")
        v1 = await reg.publish(b1, strategy_id="sma_cross", params={}, universe=["AAPL"])
        b2 = await reg.create_bot(name="TSLA bot", owner_id="owner-1")
        v2 = await reg.publish(b2, strategy_id="sma_cross", params={}, universe=["TSLA"])

        svc = PortfolioService(uow.session, history_bars=2000)
        result = await svc.backtest(
            [Allocation(b1, v1, 1.0), Allocation(b2, v2, 3.0)],
            capital=Decimal("100000"),
        )

        # Two legs, weights normalized to sum to 1 (1:3 -> 0.25 / 0.75).
        assert len(result.legs) == 2
        assert abs(sum(leg["weight"] for leg in result.legs) - 1.0) < 1e-6
        assert {leg["symbol"] for leg in result.legs} == {"AAPL", "TSLA"}

        # Combined curve + stats are well-formed; the portfolio starts at the capital.
        assert len(result.equity) > 1
        assert abs(result.equity[0]["value"] - 100000) < 1.0
        assert {"equity", "net_pnl", "return_pct", "max_drawdown_pct", "sharpe", "num_trades"} <= (
            result.perf.keys()
        )
        assert result.perf["num_trades"] == sum(leg["perf"]["num_trades"] for leg in result.legs)

        await uow.rollback()

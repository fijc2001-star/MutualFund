"""QualificationService gates lifecycle transitions on assessed performance."""

from __future__ import annotations

from decimal import Decimal

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.performance import PerformanceRecord
from mutualfund.lifecycle.lifecycle import BotLifecycle, BotState
from mutualfund.lifecycle.qualification import QualificationInput
from mutualfund.lifecycle.service import QualificationService
from mutualfund.strategy.models import BotRegistry, BotVersion


def _record(*, net_pnl: str, sharpe: str | None, max_dd: str, num_trades: int) -> PerformanceRecord:
    return PerformanceRecord(
        starting_cash=Decimal("100000"),
        net_pnl=Decimal(net_pnl),
        return_pct=Decimal("10"),
        max_drawdown_pct=Decimal(max_dd),
        num_trades=num_trades,
        win_rate=Decimal("0.6"),
        sharpe=Decimal(sharpe) if sharpe is not None else None,
    )


_PASS = QualificationInput(
    _record(net_pnl="5000", sharpe="1.2", max_dd="8", num_trades=40), evaluation_days=60
)
_FAIL = QualificationInput(
    _record(net_pnl="-2000", sharpe="0.1", max_dd="35", num_trades=3), evaluation_days=5
)


async def _evaluating_version(uow: UnitOfWork) -> BotVersion:
    registry = BotRegistry(uow.session)
    bot = await registry.create_bot(name="Bot", owner_id="owner-1")
    version = await registry.publish(bot, strategy_id="sma_cross", params={})
    await BotLifecycle(uow.session).transition(version, BotState.EVALUATION, reason="start eval")
    return version


async def test_passing_record_promotes_to_listed(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        version = await _evaluating_version(uow)
        result = await QualificationService(uow.session).evaluate(version, _PASS)

        assert result.passed
        assert version.state == BotState.LISTED.value
        # The exact bar it cleared is recorded on the version.
        assert version.qualified_policy == "baseline"
        assert version.qualified_policy_version == 1


async def test_failing_record_delists_in_evaluation(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        version = await _evaluating_version(uow)
        result = await QualificationService(uow.session).evaluate(version, _FAIL)

        assert not result.passed
        assert version.state == BotState.DELISTED.value
        assert version.qualified_policy is None


async def test_breach_suspends_a_listed_bot(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        version = await _evaluating_version(uow)
        service = QualificationService(uow.session)
        await service.evaluate(version, _PASS)  # Evaluation -> Listed
        assert version.state == BotState.LISTED.value

        await service.evaluate(version, _FAIL)  # breach while Listed -> Suspended
        assert version.state == BotState.SUSPENDED.value

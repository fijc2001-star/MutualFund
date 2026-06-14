"""The bot state machine allows/blocks the right transitions and audits each change."""

from __future__ import annotations

import pytest

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.lifecycle.lifecycle import BotLifecycle, BotState, IllegalTransitionError
from mutualfund.strategy.models import BotRegistry


def test_allowed_transitions() -> None:
    assert BotLifecycle.can_transition(BotState.DRAFT, BotState.EVALUATION)
    assert BotLifecycle.can_transition(BotState.EVALUATION, BotState.LISTED)
    assert BotLifecycle.can_transition(BotState.LISTED, BotState.SUSPENDED)
    assert BotLifecycle.can_transition(BotState.SUSPENDED, BotState.LISTED)
    assert BotLifecycle.can_transition(BotState.DELISTED, BotState.LIQUIDATION)


def test_blocked_transitions() -> None:
    assert not BotLifecycle.can_transition(BotState.DRAFT, BotState.LISTED)
    assert not BotLifecycle.can_transition(BotState.LISTED, BotState.DRAFT)
    assert not BotLifecycle.can_transition(BotState.RETIRED, BotState.LISTED)


async def _new_version(uow: UnitOfWork):
    registry = BotRegistry(uow.session)
    bot = await registry.create_bot(name="Bot", owner_id="owner-1")
    return await registry.publish(bot, strategy_id="sma_cross", params={})


async def test_transition_persists_state(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        version = await _new_version(uow)
        assert version.state == BotState.DRAFT.value

        lifecycle = BotLifecycle(uow.session)
        await lifecycle.transition(version, BotState.EVALUATION, reason="ready")
        assert version.state == BotState.EVALUATION.value


async def test_illegal_transition_raises(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        version = await _new_version(uow)
        lifecycle = BotLifecycle(uow.session)
        with pytest.raises(IllegalTransitionError):
            await lifecycle.transition(version, BotState.LISTED, reason="skip the queue")
        assert version.state == BotState.DRAFT.value

"""Publishing a bot forks an immutable version; prior versions are never mutated."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.strategy.models import BotRegistry


async def test_publish_forks_immutable_versions(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.create_bot(name="My SMA Bot", owner_id="owner-1")
        assert bot.current_version == 0
        assert bot.state == "draft"

        v1 = await registry.publish(
            bot, strategy_id="sma_cross", params={"fast": 9, "slow": 21}, universe=["AAPL"]
        )
        v2 = await registry.publish(
            bot, strategy_id="sma_cross", params={"fast": 5, "slow": 20}, universe=["AAPL"]
        )

        assert (v1.version, v2.version) == (1, 2)
        assert bot.current_version == 2
        # Prior version is frozen — publishing v2 did not edit v1's params.
        assert v1.params == {"fast": 9, "slow": 21}
        assert v2.params == {"fast": 5, "slow": 20}

        versions = await registry.versions(bot.id)
        assert [v.version for v in versions] == [1, 2]


async def test_publish_normalizes_params_through_schema(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.create_bot(name="Defaults Bot", owner_id="owner-1")
        version = await registry.publish(bot, strategy_id="sma_cross", params={})
        # Missing params are filled from the schema defaults and stored frozen.
        assert version.params == {"fast": 9, "slow": 21}
        assert version.definition.strategy_id == "sma_cross"


async def test_publish_rejects_bad_params(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.create_bot(name="Bad Bot", owner_id="owner-1")
        with pytest.raises(ValidationError):
            await registry.publish(bot, strategy_id="sma_cross", params={"fast": 30, "slow": 5})
        assert bot.current_version == 0
        assert await registry.versions(bot.id) == []

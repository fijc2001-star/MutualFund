"""Publishing requires a Listed bot and snapshots its real backtest record."""

from __future__ import annotations

import pytest

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.marketplace.service import ListingError, MarketplaceService
from mutualfund.strategy.models import BotRegistry


async def _listed_bot(session, *, owner_id: str = "owner-1", symbol: str = "MSFT"):
    registry = BotRegistry(session)
    bot = await registry.create_bot(name="My MSFT Bot", owner_id=owner_id)
    version = await registry.publish(
        bot, strategy_id="sma_cross", params={"fast": 9, "slow": 21}, universe=[symbol]
    )
    bot.state = "listed"  # simulate having cleared qualification (M-C)
    return bot, version


async def test_publish_requires_listed_bot(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.create_bot(name="Draft Bot", owner_id="owner-1")
        version = await registry.publish(
            bot, strategy_id="sma_cross", params={"fast": 9, "slow": 21}, universe=["MSFT"]
        )
        svc = MarketplaceService(uow.session, history_bars=2000)
        with pytest.raises(ListingError):
            await svc.publish(bot, version, title="Nope")  # still draft
        await uow.rollback()


async def test_publish_snapshots_record_and_lists(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        bot, version = await _listed_bot(uow.session)
        svc = MarketplaceService(uow.session, history_bars=2000)
        listing = await svc.publish(bot, version, title="My MSFT Bot", price_cents=500)

        assert listing.symbol == "MSFT"
        assert listing.billing_period == "monthly"
        assert listing.status == "active"
        # Track record is the real backtest perf, not a designer claim.
        assert {"return_pct", "num_trades", "max_drawdown_pct"} <= listing.track_record.keys()

        active = await svc.list_active()
        assert [item.id for item in active] == [listing.id]
        await uow.rollback()


async def test_free_listing_has_free_period(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        bot, version = await _listed_bot(uow.session)
        svc = MarketplaceService(uow.session, history_bars=2000)
        listing = await svc.publish(bot, version, title="Free Bot", price_cents=0)
        assert listing.billing_period == "free"
        await uow.rollback()


async def test_republish_updates_existing_listing(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        bot, version = await _listed_bot(uow.session)
        svc = MarketplaceService(uow.session, history_bars=2000)
        first = await svc.publish(bot, version, title="V1", price_cents=100)
        second = await svc.publish(bot, version, title="V1 renamed", price_cents=200)

        assert first.id == second.id  # one listing per bot — re-publish updates in place
        assert second.title == "V1 renamed"
        assert second.price_cents == 200
        assert len(await svc.list_active()) == 1
        await uow.rollback()


async def test_paused_listing_drops_from_browse(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        bot, version = await _listed_bot(uow.session)
        svc = MarketplaceService(uow.session, history_bars=2000)
        listing = await svc.publish(bot, version, title="Pause me")
        await svc.set_status(listing, "paused")

        assert await svc.list_active() == []
        assert len(await svc.for_owner("owner-1")) == 1  # still visible to the owner
        await uow.rollback()

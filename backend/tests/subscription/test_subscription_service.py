"""Subscribing to a listing materializes the bot's signal stream and records billing."""

from __future__ import annotations

from sqlalchemy import select

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.marketplace.models import BillingEntry, Listing
from mutualfund.marketplace.service import MarketplaceService
from mutualfund.strategy.models import BotRegistry
from mutualfund.subscription.service import SubscriptionService

_HIST = 2000


async def _list_bot(session, *, owner_id="designer-1", price_cents=0, symbol="AAPL"):
    """Create a Listed bot and publish it; return (listing, definition)."""
    registry = BotRegistry(session)
    bot = await registry.create_bot(name="Bot", owner_id=owner_id)
    version = await registry.publish(
        bot, strategy_id="sma_cross", params={"fast": 9, "slow": 21}, universe=[symbol]
    )
    bot.state = "listed"
    listing = await MarketplaceService(session, history_bars=_HIST).publish(
        bot, version, title="Bot", price_cents=price_cents
    )
    return listing, version.definition


async def test_subscribe_materializes_and_replays(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        listing, definition = await _list_bot(uow.session)
        svc = SubscriptionService(uow.session, history_bars=_HIST)
        sub = await svc.subscribe(listing, definition, subscriber="buyer-1")
        assert sub.stream_id == f"bot:{listing.bot_id}"

        candles, signals = await svc.replay(sub)
        assert len(candles) > 0
        assert len(signals) > 0

        # Replay reads the PERSISTED, hash-chained signals — not a fresh recomputation.
        ledger = EventLedger(uow.session)
        events = await ledger.replay(sub.stream_id)
        sig_events = [e for e in events if e.event_type is LedgerEventType.SIGNAL]
        assert len(sig_events) == len(signals)
        assert (await ledger.verify(sub.stream_id)).ok

        first = signals[0]
        assert first["side"] in {"buy", "sell"}
        assert "price" in first and "rationale" in first
        await uow.rollback()


async def test_subscribe_is_idempotent(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        listing, definition = await _list_bot(uow.session)
        svc = SubscriptionService(uow.session, history_bars=_HIST)
        a = await svc.subscribe(listing, definition, subscriber="buyer-1")
        _, signals_a = await svc.replay(a)
        b = await svc.subscribe(listing, definition, subscriber="buyer-1")
        _, signals_b = await svc.replay(b)

        assert a.id == b.id
        assert len(signals_a) == len(signals_b)
        await uow.rollback()


async def test_free_subscription_records_no_billing(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        listing, definition = await _list_bot(uow.session, price_cents=0)
        await SubscriptionService(uow.session, history_bars=_HIST).subscribe(
            listing, definition, subscriber="buyer-1"
        )
        entries = (await uow.session.execute(select(BillingEntry))).scalars().all()
        assert entries == []
        await uow.rollback()


async def test_paid_subscription_records_fee_split_once(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        listing, definition = await _list_bot(uow.session, owner_id="designer-1", price_cents=1000)
        svc = SubscriptionService(uow.session, history_bars=_HIST)
        await svc.subscribe(listing, definition, subscriber="buyer-1")
        await svc.subscribe(listing, definition, subscriber="buyer-1")  # idempotent: no 2nd charge

        entries = (await uow.session.execute(select(BillingEntry))).scalars().all()
        assert len(entries) == 1
        e = entries[0]
        # Default platform fee is 20%.
        assert (e.gross_cents, e.platform_fee_cents, e.designer_net_cents) == (1000, 200, 800)

        earnings = await MarketplaceService(uow.session).earnings_for("designer-1")
        assert earnings == {
            "subscriptions": 1, "gross_cents": 1000,
            "platform_fee_cents": 200, "net_cents": 800,
        }
        await uow.rollback()


async def test_unsubscribe_removes_subscription(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        listing, definition = await _list_bot(uow.session)
        svc = SubscriptionService(uow.session, history_bars=_HIST)
        sub = await svc.subscribe(listing, definition, subscriber="buyer-1")
        await svc.unsubscribe(sub)

        assert await svc.for_subscriber("buyer-1") == []
        # The bot's shared signal stream is untouched (it belongs to the bot, not the sub).
        remaining = (await uow.session.execute(select(Listing))).scalars().all()
        assert len(remaining) == 1
        await uow.rollback()

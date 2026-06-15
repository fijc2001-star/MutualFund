"""Subscribing materializes the bot's signal stream once; replay reads the persisted record."""

from __future__ import annotations

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.subscription.service import SubscriptionService


async def test_subscribe_materializes_and_replays(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        svc = SubscriptionService(uow.session, history_bars=2000)
        sub = await svc.subscribe("AAPL")
        assert sub.stream_id == "bot:AAPL:sma_cross"

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
        assert "price" in first
        assert "rationale" in first


async def test_subscribe_is_idempotent(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        svc = SubscriptionService(uow.session, history_bars=2000)
        a = await svc.subscribe("AAPL")
        _, signals_a = await svc.replay(a)

        # Subscribing again returns the same subscription and does not duplicate the stream.
        b = await svc.subscribe("AAPL")
        _, signals_b = await svc.replay(b)

        assert a.id == b.id
        assert len(signals_a) == len(signals_b)

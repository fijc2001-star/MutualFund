"""Hash-chain integrity, tamper detection, replay, and tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from mutualfund.foundation.clock import FixedClock
from mutualfund.foundation.ids import TenantId, new_id
from mutualfund.foundation.tenant import TenantContext
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEvent, LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.ledger.models import LedgerEntry

CLOCK = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))


def _event(stream: str, n: int) -> LedgerEvent:
    return LedgerEvent(stream, LedgerEventType.SIGNAL, {"n": n}, CLOCK.now())


async def test_append_builds_valid_chain_and_verifies(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        for n in range(5):
            await led.append(_event("s1", n))
        result = await led.verify("s1")
        assert result.ok and result.broken_seq is None
        events = await led.replay("s1")
        assert [e.payload["n"] for e in events] == [0, 1, 2, 3, 4]


async def test_tamper_is_detected(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        for n in range(4):
            await led.append(_event("s2", n))
        # Tamper with a stored payload (seq 1) directly.
        entry = await uow.session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.stream_id == "s2", LedgerEntry.seq == 1
            )
        )
        assert entry is not None
        entry.payload = {"n": 999}
        await uow.session.flush()

        result = await led.verify("s2")
        assert not result.ok
        assert result.broken_seq == 1


async def test_streams_and_tenants_are_isolated(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        await led.append(_event("a", 0))
        await led.append(_event("a", 1))
        await led.append(_event("b", 0))
        assert len(await led.replay("a")) == 2
        assert len(await led.replay("b")) == 1
    TenantContext.reset(token)

    other = TenantId(new_id())
    token2 = TenantContext.set(other)
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        assert await led.replay("a") == []  # other tenant sees nothing
    TenantContext.reset(token2)

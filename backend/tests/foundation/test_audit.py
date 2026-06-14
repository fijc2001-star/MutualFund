"""Audit log append + deterministic timestamp via injected clock."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from mutualfund.foundation.audit import AuditEvent, AuditLog
from mutualfund.foundation.clock import FixedClock
from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork


async def test_record_appends_with_fixed_clock(tenant_ctx: TenantId) -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    async with UnitOfWork() as uow:
        log = AuditLog(uow.session, clock)
        evt = await log.record("user.login", actor="u1", payload={"ok": True})
        assert evt.created_at == clock.now()
        assert evt.tenant_id == tenant_ctx

    async with UnitOfWork() as uow:
        rows = (
            await uow.session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "user.login")
            )
        ).scalars().all()
        assert any(r.payload == {"ok": True} for r in rows)

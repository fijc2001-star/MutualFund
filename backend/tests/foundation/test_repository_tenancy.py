"""The critical tenancy test: cross-tenant access must be impossible."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mutualfund.foundation.audit import AuditEvent
from mutualfund.foundation.ids import TenantId, new_id
from mutualfund.foundation.repository import CrossTenantAccessError, TenantRepository
from mutualfund.foundation.tenant import TenantContext
from mutualfund.foundation.uow import UnitOfWork


def _event() -> AuditEvent:
    return AuditEvent(
        id=new_id(),
        event_type="test.event",
        actor="tester",
        payload={},
        created_at=datetime.now(timezone.utc),
    )


async def test_get_is_scoped_to_tenant(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    async with UnitOfWork() as uow:
        repo: TenantRepository[AuditEvent] = TenantRepository(uow.session, AuditEvent)
        saved = await repo.add(_event())
        event_id = saved.id
        assert await repo.get(event_id) is not None
    TenantContext.reset(token)

    other = TenantId(new_id())
    token2 = TenantContext.set(other)
    async with UnitOfWork() as uow:
        repo2: TenantRepository[AuditEvent] = TenantRepository(uow.session, AuditEvent)
        assert await repo2.get(event_id) is None  # another tenant cannot read it
    TenantContext.reset(token2)


async def test_cross_tenant_write_is_blocked(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    async with UnitOfWork() as uow:
        repo: TenantRepository[AuditEvent] = TenantRepository(uow.session, AuditEvent)
        evt = _event()
        evt.tenant_id = new_id()  # explicitly a different tenant
        with pytest.raises(CrossTenantAccessError):
            await repo.add(evt)
    TenantContext.reset(token)

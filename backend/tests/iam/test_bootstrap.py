from __future__ import annotations

from sqlalchemy import select

from mutualfund.config import get_settings
from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.tenant import TenantContext
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.iam.bootstrap import ensure_root_admin
from mutualfund.iam.models import User
from mutualfund.iam.roles import Role


async def test_root_admin_created_and_idempotent() -> None:
    settings = get_settings()
    assert settings.root_admin_email is not None
    tid = TenantId(settings.default_tenant_id)
    token = TenantContext.set(tid)
    try:
        async with UnitOfWork() as uow:
            created = await ensure_root_admin(uow.session)
            assert created is not None
            assert created.role == Role.ROOT_ADMIN.value

        async with UnitOfWork() as uow:
            await ensure_root_admin(uow.session)  # second call
            rows = (
                await uow.session.execute(
                    select(User).where(
                        User.tenant_id == tid,
                        User.email == settings.root_admin_email.lower(),
                    )
                )
            ).scalars().all()
            assert len(rows) == 1  # idempotent, no duplicate
    finally:
        TenantContext.reset(token)

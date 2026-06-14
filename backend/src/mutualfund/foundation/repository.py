"""Generic tenant-scoped repository — the core multi-tenancy guarantee.

Every read is filtered by the current TenantContext; every write is stamped with /
validated against it. Cross-tenant access raises (ARCHITECTURE §5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import TenantScoped
from .tenant import TenantContext


class CrossTenantAccessError(PermissionError):
    pass


T = TypeVar("T", bound=TenantScoped)


class TenantRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: AsyncSession, model: type[T] | None = None) -> None:
        self.session = session
        if model is not None:
            self.model = model
        if not hasattr(self, "model"):
            raise TypeError("TenantRepository requires a model (subclass attr or ctor arg)")

    async def add(self, entity: T) -> T:
        tid = TenantContext.get()
        current = getattr(entity, "tenant_id", None)
        if current in (None, ""):
            entity.tenant_id = tid
        elif current != tid:
            raise CrossTenantAccessError("Refusing to persist an entity for another tenant")
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id_: str) -> T | None:
        tid = TenantContext.get()
        stmt = select(self.model).where(
            self.model.id == id_,  # type: ignore[attr-defined]
            self.model.tenant_id == tid,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[T]:
        tid = TenantContext.get()
        stmt = select(self.model).where(self.model.tenant_id == tid)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete(self, entity: T) -> None:
        tid = TenantContext.get()
        if getattr(entity, "tenant_id", None) != tid:
            raise CrossTenantAccessError("Refusing to delete an entity for another tenant")
        await self.session.delete(entity)
        await self.session.flush()

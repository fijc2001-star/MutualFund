"""Append-only audit log (REQUIREMENTS §5.11, §7).

No UPDATE/DELETE is exposed — entries are write-once. This is both a trust feature
and a precursor to the tamper-resistant ledger (M10) built later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .clock import Clock, SystemClock
from .db import Base, Entity, TenantScoped
from .ids import new_id
from .tenant import TenantContext


class AuditEvent(Base, Entity, TenantScoped):
    __tablename__ = "audit_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog:
    def __init__(self, session: AsyncSession, clock: Clock | None = None) -> None:
        self.session = session
        self.clock = clock or SystemClock()

    async def record(
        self, event_type: str, actor: str, payload: dict[str, Any] | None = None
    ) -> AuditEvent:
        event = AuditEvent(
            id=new_id(),
            tenant_id=TenantContext.get(),
            event_type=event_type,
            actor=actor,
            payload=payload or {},
            created_at=self.clock.now(),
        )
        self.session.add(event)
        await self.session.flush()
        return event

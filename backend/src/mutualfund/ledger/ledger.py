"""EventLedger: append-only writes, tamper-evident verification, replay.

Each entry's hash = sha256(prev_hash + canonical(event)). Altering any past payload
breaks every subsequent hash, so verify() detects tampering by anyone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..foundation.clock import Clock, SystemClock
from ..foundation.ids import new_id
from ..foundation.tenant import TenantContext
from .event import GENESIS_HASH, LedgerEvent, LedgerEventType, chain_hash
from .models import LedgerEntry


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    broken_seq: int | None
    detail: str


class EventLedger:
    def __init__(self, session: AsyncSession, clock: Clock | None = None) -> None:
        self.session = session
        self.clock = clock or SystemClock()

    async def _entries(self, stream_id: str) -> Sequence[LedgerEntry]:
        tid = TenantContext.get()
        stmt = (
            select(LedgerEntry)
            .where(LedgerEntry.tenant_id == tid, LedgerEntry.stream_id == stream_id)
            .order_by(LedgerEntry.seq)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def append(self, event: LedgerEvent) -> LedgerEntry:
        tid = TenantContext.get()
        last = await self.session.scalar(
            select(LedgerEntry)
            .where(LedgerEntry.tenant_id == tid, LedgerEntry.stream_id == event.stream_id)
            .order_by(LedgerEntry.seq.desc())
            .limit(1)
        )
        prev_hash = last.hash if last is not None else GENESIS_HASH
        seq = (last.seq + 1) if last is not None else 0
        entry = LedgerEntry(
            id=new_id(),
            tenant_id=tid,
            stream_id=event.stream_id,
            seq=seq,
            event_type=event.event_type.value,
            payload=event.payload,
            ts=event.ts,
            prev_hash=prev_hash,
            hash=chain_hash(prev_hash, event),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def replay(self, stream_id: str) -> list[LedgerEvent]:
        return [
            LedgerEvent(
                stream_id=e.stream_id,
                event_type=LedgerEventType(e.event_type),
                payload=e.payload,
                ts=e.ts,
            )
            for e in await self._entries(stream_id)
        ]

    async def verify(self, stream_id: str) -> VerificationResult:
        prev = GENESIS_HASH
        for entry in await self._entries(stream_id):
            event = LedgerEvent(
                stream_id=entry.stream_id,
                event_type=LedgerEventType(entry.event_type),
                payload=entry.payload,
                ts=entry.ts,
            )
            if entry.prev_hash != prev:
                return VerificationResult(False, entry.seq, "prev_hash mismatch")
            if entry.hash != chain_hash(prev, event):
                return VerificationResult(False, entry.seq, "hash mismatch (payload tampered)")
            prev = entry.hash
        return VerificationResult(True, None, "intact")

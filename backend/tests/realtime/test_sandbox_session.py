"""The live sandbox session emits snapshot/bar/perf and real fills onto the ledger."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.realtime.sandbox_session import SandboxSession


async def test_session_streams_and_writes_real_fills(tenant_ctx: TenantId) -> None:
    sent: list[dict[str, Any]] = []

    async def collect(msg: dict[str, Any]) -> None:
        sent.append(msg)

    async with UnitOfWork() as uow:
        session = SandboxSession(uow, "AAPL", Decimal(100_000))
        await session.run(collect, interval=0.0, max_ticks=120)
        stream_id = session._stream_id

        types = [m["type"] for m in sent]
        assert types[0] == "snapshot"
        assert "bar" in types
        assert "perf" in types

        # perf payload is well-formed
        perf = next(m["perf"] for m in sent if m["type"] == "perf")
        assert {"equity", "cash", "net_pnl", "num_trades"} <= perf.keys()

        # The SMA-cross strategy should have traded, writing fills to the ledger,
        # and the ledger must verify intact.
        ledger = EventLedger(uow.session)
        events = await ledger.replay(stream_id)
        fills = [e for e in events if e.event_type is LedgerEventType.FILL]
        signal_msgs = [m for m in sent if m["type"] == "signal"]
        assert len(fills) == len(signal_msgs)
        assert fills, "the SMA-cross bot should have traded under default risk limits"
        assert (await ledger.verify(stream_id)).ok


async def test_kill_switch_blocks_all_execution(tenant_ctx: TenantId) -> None:
    """A hard guardrail (kill switch) must block every order: no fills, blocks surfaced."""
    sent: list[dict[str, Any]] = []

    async def collect(msg: dict[str, Any]) -> None:
        sent.append(msg)

    async with UnitOfWork() as uow:
        session = SandboxSession(uow, "AAPL", Decimal(100_000), kill_switch=True)
        await session.run(collect, interval=0.0, max_ticks=120)
        stream_id = session._stream_id

        ledger = EventLedger(uow.session)
        events = await ledger.replay(stream_id)
        fills = [e for e in events if e.event_type is LedgerEventType.FILL]
        blocked = [m for m in sent if m["type"] == "blocked"]

        assert fills == []
        assert blocked, "the bot tried to trade but every order was guardrail-blocked"
        assert all(b["blocked"]["kind"] == "guardrail" for b in blocked)
        assert (await ledger.verify(stream_id)).ok

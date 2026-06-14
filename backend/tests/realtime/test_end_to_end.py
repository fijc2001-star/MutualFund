"""Phase 3 end-to-end: one BotVersion flows through the whole pipeline in a single run.

engine → sizing → risk → sandbox → ledger → performance → qualification → lifecycle,
with bars/fills/perf/lifecycle streamed to the client.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.ledger.performance import PerformanceCalculator
from mutualfund.lifecycle.lifecycle import BotState
from mutualfund.lifecycle.qualification import MinPeriod, MinTrades, QualificationPolicy
from mutualfund.realtime.sandbox_session import SandboxSession

# A policy that passes once the bot has actually traded — keeps the assertion deterministic
# regardless of the demo feed's random P&L, while still exercising the real gate.
_TRADED = QualificationPolicy("e2e", 1, [MinPeriod(0), MinTrades(1)])


async def test_full_pipeline_promotes_a_traded_bot(tenant_ctx: TenantId) -> None:
    sent: list[dict[str, Any]] = []

    async def collect(msg: dict[str, Any]) -> None:
        sent.append(msg)

    async with UnitOfWork() as uow:
        session = SandboxSession(uow, "AAPL", Decimal(100_000), policy=_TRADED)
        await session.run(collect, interval=0.0, max_ticks=120)
        version = session._version
        stream_id = session._stream_id

        assert version is not None

        # --- streaming contract: snapshot, bars, perf, and lifecycle all surfaced ---
        types = [m["type"] for m in sent]
        assert types[0] == "snapshot"
        assert "bar" in types and "perf" in types

        lifecycle_msgs = [m["lifecycle"] for m in sent if m["type"] == "lifecycle"]
        assert lifecycle_msgs[0]["state"] == BotState.EVALUATION.value
        final = lifecycle_msgs[-1]
        assert final["state"] == BotState.LISTED.value
        assert final["qualification"]["passed"] is True
        assert final["qualification"]["policy"] == "e2e"

        # --- ledger: fills written and hash chain intact ---
        ledger = EventLedger(uow.session)
        events = await ledger.replay(stream_id)
        fills = [e for e in events if e.event_type is LedgerEventType.FILL]
        signal_msgs = [m for m in sent if m["type"] == "signal"]
        assert fills, "the SMA-cross bot should have traded"
        assert len(fills) == len(signal_msgs)
        assert (await ledger.verify(stream_id)).ok

        # --- performance derived from the same ledger matches the trades taken ---
        record = PerformanceCalculator().from_events(events, Decimal(100_000))
        assert record.num_trades == sum(1 for m in signal_msgs if m["signal"]["side"] == "sell")

        # --- lifecycle: the bot was promoted and the policy bar is stamped on the version ---
        assert version.state == BotState.LISTED.value
        assert version.qualified_policy == "e2e"
        assert version.qualified_policy_version == 1

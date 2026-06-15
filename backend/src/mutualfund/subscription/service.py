"""SubscriptionService — materialize a bot's signal stream once, then replay it per window.

`subscribe` finds-or-creates a subscription and ensures the bot's signal stream is
materialized: the deterministic history is run through the SignalEngine and each signal is
persisted as a hash-chained SIGNAL event on the EventLedger (the tamper-evident track record).
`replay` regenerates the candle context deterministically and reads the *persisted* signals
from `started_at` — so it reads the stored record, not a fresh recomputation.

Note (prototype): bars are regenerated from the deterministic demo feed rather than persisted
(they aren't the trust artifact and would bloat the ledger); a real provider would persist or
re-fetch them. Signals — the thing a buyer relies on — are persisted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..foundation.clock import Clock, SystemClock
from ..foundation.instrument import AssetClass, Instrument
from ..foundation.repository import TenantRepository
from ..foundation.tenant import TenantContext
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.ledger import EventLedger
from ..realtime.demo import DemoBar, DemoFeed, bar_dict
from ..signals.engine import SignalEngine
from ..signals.signal import Action
from ..strategy.strategy import BotDefinition, StrategyContext
from .models import Subscription

_DEFAULT_HISTORY_BARS = 14_400
_SHORT = 9
_LONG = 21


def _side(action: Action) -> str:
    return "buy" if action is Action.BUY else "sell"


class SubscriptionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        history_bars: int = _DEFAULT_HISTORY_BARS,
        clock: Clock | None = None,
        engine: SignalEngine | None = None,
    ) -> None:
        self._session = session
        self._subs: TenantRepository[Subscription] = TenantRepository(session, Subscription)
        self._ledger = EventLedger(session, clock)
        self._engine = engine or SignalEngine()
        self._clock = clock or SystemClock()
        self._history_bars = history_bars

    async def subscribe(
        self, symbol: str, *, strategy_id: str = "sma_cross", subscriber: str = "demo"
    ) -> Subscription:
        stream_id = f"bot:{symbol}:{strategy_id}"
        bars = DemoFeed(symbol).snapshot(self._history_bars)

        sub = await self._find(subscriber, symbol, strategy_id)
        if sub is None:
            sub = await self._subs.add(
                Subscription(
                    subscriber=subscriber,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    stream_id=stream_id,
                    started_at=datetime.fromtimestamp(bars[0].time, UTC),
                    created_at=self._clock.now(),
                )
            )
        await self._materialize(stream_id, symbol, bars)
        return sub

    async def replay(self, sub: Subscription) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (candles, signals) for the bot's stream from the subscription's start."""
        start = int(sub.started_at.timestamp())
        bars = DemoFeed(sub.symbol).snapshot(self._history_bars)
        candles = [bar_dict(b) for b in bars if b.time >= start]

        events = await self._ledger.replay(sub.stream_id)
        signals = [
            {
                "time": e.payload["time"],
                "side": e.payload["side"],
                "price": float(e.payload["price"]),
                "reason": e.payload.get("thesis") or e.payload["side"],
                "rationale": {
                    "thesis": e.payload.get("thesis", ""),
                    "indicators": e.payload.get("indicators", []),
                    "invalidation": e.payload.get("invalidation"),
                },
            }
            for e in events
            if e.event_type is LedgerEventType.SIGNAL and int(e.payload["time"]) >= start
        ]
        return candles, signals

    async def _find(
        self, subscriber: str, symbol: str, strategy_id: str
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.tenant_id == TenantContext.get(),
            Subscription.subscriber == subscriber,
            Subscription.symbol == symbol,
            Subscription.strategy_id == strategy_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _materialize(self, stream_id: str, symbol: str, bars: list[DemoBar]) -> None:
        """Run the bot over the history once and persist its signals (idempotent)."""
        existing = await self._ledger.replay(stream_id)
        if any(e.event_type is LedgerEventType.SIGNAL for e in existing):
            return  # already materialized

        definition = BotDefinition("sma_cross", {"fast": _SHORT, "slow": _LONG})
        instrument = Instrument(symbol, AssetClass.EQUITY)
        closes: list[float] = []
        position = Decimal(0)
        for bar in bars:
            closes.append(bar.close)
            ctx = StrategyContext(instrument, closes, position=position)
            for sig in self._engine.run(definition, ctx):
                rationale = sig.rationale
                await self._ledger.append(
                    LedgerEvent(
                        stream_id=stream_id,
                        event_type=LedgerEventType.SIGNAL,
                        payload={
                            "time": bar.time,
                            "side": _side(sig.action),
                            "price": str(bar.close),
                            "thesis": rationale.thesis if rationale else "",
                            "indicators": rationale.indicators if rationale else [],
                            "invalidation": rationale.invalidation if rationale else None,
                        },
                        ts=datetime.fromtimestamp(bar.time, UTC),
                    )
                )
                position = Decimal(1) if sig.action is Action.BUY else Decimal(0)

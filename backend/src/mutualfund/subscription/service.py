"""SubscriptionService — subscribe a user to a listing, then replay the bot's signal stream.

`subscribe` finds-or-creates the subscription, records a billing entry (with the platform-fee
split) the first time a *paid* listing is joined, and materializes the bot's signal stream once:
the deterministic history is run through the SignalEngine and each signal is persisted as a
hash-chained SIGNAL event on the EventLedger (the tamper-evident track record). `replay`
regenerates the candle context deterministically and reads the *persisted* signals from the
subscription's start — the stored record, not a fresh recomputation.

Note (prototype): bars are regenerated from the deterministic demo feed rather than persisted
(they aren't the trust artifact); signals — the thing a buyer relies on — are persisted. Billing
is a recorded accounting entry: the platform never custodies money (REQUIREMENTS).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..foundation.clock import Clock, SystemClock
from ..foundation.instrument import AssetClass, Instrument
from ..foundation.repository import TenantRepository
from ..foundation.tenant import TenantContext
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.ledger import EventLedger
from ..marketplace.models import BillingEntry, Listing
from ..realtime.demo import DemoBar, DemoFeed, bar_dict
from ..signals.engine import SignalEngine
from ..signals.signal import Action
from ..strategy.strategy import BotDefinition, StrategyContext
from .models import Subscription

_DEFAULT_HISTORY_BARS = 14_400


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
        self._billing: TenantRepository[BillingEntry] = TenantRepository(session, BillingEntry)
        self._ledger = EventLedger(session, clock)
        self._engine = engine or SignalEngine()
        self._clock = clock or SystemClock()
        self._history_bars = history_bars

    async def subscribe(
        self, listing: Listing, definition: BotDefinition, *, subscriber: str
    ) -> Subscription:
        """Join a listing: find-or-create the subscription, charge once if paid, materialize."""
        stream_id = f"bot:{listing.bot_id}"
        bars = DemoFeed(listing.symbol).snapshot(self._history_bars)

        sub = await self._find(subscriber, listing.id)
        if sub is None:
            sub = await self._subs.add(
                Subscription(
                    subscriber=subscriber,
                    listing_id=listing.id,
                    symbol=listing.symbol,
                    strategy_id=listing.strategy_id,
                    stream_id=stream_id,
                    started_at=datetime.fromtimestamp(bars[0].time, UTC),
                    created_at=self._clock.now(),
                )
            )
            if listing.price_cents > 0:
                await self._charge(sub, listing, subscriber)
        await self._materialize(stream_id, listing.symbol, definition, bars)
        return sub

    async def materialize_stream(
        self, stream_id: str, symbol: str, definition: BotDefinition
    ) -> None:
        """Ensure a bot's signal stream is materialized (used by the dashboard replay demo)."""
        bars = DemoFeed(symbol).snapshot(self._history_bars)
        await self._materialize(stream_id, symbol, definition, bars)

    async def for_subscriber(self, subscriber: str) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.tenant_id == TenantContext.get(),
                Subscription.subscriber == subscriber,
            )
            .order_by(Subscription.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get(self, subscription_id: str) -> Subscription | None:
        return await self._subs.get(subscription_id)

    async def unsubscribe(self, sub: Subscription) -> None:
        await self._subs.delete(sub)

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

    async def _charge(self, sub: Subscription, listing: Listing, subscriber: str) -> None:
        gross = listing.price_cents
        pct = get_settings().platform_fee_pct
        fee = int((Decimal(gross) * pct).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        await self._billing.add(
            BillingEntry(
                subscription_id=sub.id,
                listing_id=listing.id,
                designer_id=listing.owner_id,
                subscriber=subscriber,
                gross_cents=gross,
                platform_fee_cents=fee,
                designer_net_cents=gross - fee,
                period=listing.billing_period,
                created_at=self._clock.now(),
            )
        )

    async def _find(self, subscriber: str, listing_id: str) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.tenant_id == TenantContext.get(),
            Subscription.subscriber == subscriber,
            Subscription.listing_id == listing_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _materialize(
        self, stream_id: str, symbol: str, definition: BotDefinition, bars: list[DemoBar]
    ) -> None:
        """Run the bot over the history once and persist its signals (idempotent)."""
        existing = await self._ledger.replay(stream_id)
        if any(e.event_type is LedgerEventType.SIGNAL for e in existing):
            return  # already materialized

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

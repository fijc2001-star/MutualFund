"""MarketplaceService — publish qualified bots as listings and browse the catalog.

Publishing requires the bot to be Listed (i.e. it cleared qualification, M-C). The track record
is snapshotted by replaying the version through the same backtest pipeline used everywhere else,
so a listing's advertised performance is the real, reproducible record — not a designer's claim.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..backtest.service import BacktestService
from ..foundation.clock import Clock, SystemClock
from ..foundation.repository import TenantRepository
from ..foundation.tenant import TenantContext
from ..strategy.models import Bot, BotVersion
from .models import BillingEntry, Listing


class ListingError(ValueError):
    """Raised when a listing cannot be published (e.g. the bot is not Listed)."""


class MarketplaceService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        history_bars: int | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session = session
        self._listings: TenantRepository[Listing] = TenantRepository(session, Listing)
        self._clock = clock or SystemClock()
        self._backtest = (
            BacktestService(session, history_bars=history_bars, clock=clock)
            if history_bars is not None
            else BacktestService(session, clock=clock)
        )

    async def publish(
        self,
        bot: Bot,
        version: BotVersion,
        *,
        title: str,
        description: str = "",
        price_cents: int = 0,
        billing_period: str = "monthly",
    ) -> Listing:
        """Publish (or re-publish) a Listed bot as a marketplace listing, with a fresh record."""
        if bot.state != "listed":
            raise ListingError("bot must be Listed (pass qualification) before it can be published")
        if price_cents < 0:
            raise ListingError("price must be non-negative")

        symbol = version.universe[0] if version.universe else "AAPL"
        result = await self._backtest.run(
            symbol, strategy_id=version.strategy_id, params=dict(version.params)
        )
        period = "free" if price_cents == 0 else billing_period
        now = self._clock.now()

        existing = await self._for_bot(bot.id)
        if existing is not None:
            existing.bot_version = version.version
            existing.title = title
            existing.description = description
            existing.symbol = symbol
            existing.strategy_id = version.strategy_id
            existing.price_cents = price_cents
            existing.billing_period = period
            existing.status = "active"
            existing.track_record = result.perf
            existing.updated_at = now
            return await self._listings.add(existing)

        return await self._listings.add(
            Listing(
                bot_id=bot.id,
                bot_version=version.version,
                owner_id=bot.owner_id,
                title=title,
                description=description,
                symbol=symbol,
                strategy_id=version.strategy_id,
                price_cents=price_cents,
                billing_period=period,
                status="active",
                track_record=result.perf,
                created_at=now,
                updated_at=now,
            )
        )

    async def set_status(self, listing: Listing, status: str) -> Listing:
        if status not in ("active", "paused", "withdrawn"):
            raise ListingError(f"unknown status: {status}")
        listing.status = status
        listing.updated_at = self._clock.now()
        return await self._listings.add(listing)

    async def get(self, listing_id: str) -> Listing | None:
        return await self._listings.get(listing_id)

    async def list_active(self) -> list[Listing]:
        """All active listings in the tenant — the public browse catalog."""
        stmt = (
            select(Listing)
            .where(Listing.tenant_id == TenantContext.get(), Listing.status == "active")
            .order_by(Listing.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def for_owner(self, owner_id: str) -> list[Listing]:
        """A designer's own listings (any status)."""
        stmt = (
            select(Listing)
            .where(Listing.tenant_id == TenantContext.get(), Listing.owner_id == owner_id)
            .order_by(Listing.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def earnings_for(self, owner_id: str) -> dict[str, Any]:
        """A designer's revenue summary from recorded billing entries."""
        stmt = select(BillingEntry).where(
            BillingEntry.tenant_id == TenantContext.get(),
            BillingEntry.designer_id == owner_id,
        )
        entries = list((await self._session.execute(stmt)).scalars().all())
        gross = sum(e.gross_cents for e in entries)
        fee = sum(e.platform_fee_cents for e in entries)
        net = sum(e.designer_net_cents for e in entries)
        return {
            "subscriptions": len(entries),
            "gross_cents": gross,
            "platform_fee_cents": fee,
            "net_cents": net,
        }

    async def _for_bot(self, bot_id: str) -> Listing | None:
        stmt = select(Listing).where(
            Listing.tenant_id == TenantContext.get(), Listing.bot_id == bot_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()


def listing_dict(listing: Listing) -> dict[str, Any]:
    return {
        "id": listing.id,
        "bot_id": listing.bot_id,
        "bot_version": listing.bot_version,
        "owner_id": listing.owner_id,
        "title": listing.title,
        "description": listing.description,
        "symbol": listing.symbol,
        "strategy_id": listing.strategy_id,
        "price_cents": listing.price_cents,
        "billing_period": listing.billing_period,
        "status": listing.status,
        "track_record": listing.track_record,
        "created_at": listing.created_at.isoformat(),
    }

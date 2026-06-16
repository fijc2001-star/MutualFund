"""Portfolio REST API — backtest a weighted allocation across bots you follow or own.

Any authenticated user can allocate across the listings they're subscribed to; designers can
also allocate their own (possibly unlisted) bots. A subscribed leg runs the *exact version the
subscriber follows* (the listing's frozen version), not whatever the designer has since published.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..foundation.uow import UnitOfWork
from ..iam.deps import CurrentPrincipal
from ..marketplace.service import MarketplaceService
from ..strategy.models import BotRegistry
from ..subscription.service import SubscriptionService
from .service import Allocation, PortfolioService

router = APIRouter(tags=["portfolio"])


class AllocationItem(BaseModel):
    bot_id: str | None = None  # allocate an owned bot (designer)
    listing_id: str | None = None  # allocate a subscribed listing (any user)
    weight: float = 1.0


class PortfolioBacktestRequest(BaseModel):
    capital: float = 100_000.0
    start: int | None = None
    end: int | None = None
    allocations: list[AllocationItem]


@router.post("/portfolio/backtest")
async def portfolio_backtest(
    body: PortfolioBacktestRequest, principal: CurrentPrincipal
) -> dict[str, Any]:
    if not body.allocations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No allocations")

    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        market = MarketplaceService(uow.session)
        subscribed = {
            s.listing_id
            for s in await SubscriptionService(uow.session).for_subscriber(principal.user_id)
        }

        allocs: list[Allocation] = []
        for item in body.allocations:
            if item.listing_id is not None:
                allocs.append(
                    await _subscribed_alloc(
                        registry, market, item.listing_id, subscribed, item.weight
                    )
                )
            elif item.bot_id is not None:
                allocs.append(
                    await _owned_alloc(registry, item.bot_id, principal.user_id, item.weight)
                )
            else:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Each allocation needs a bot_id or listing_id"
                )

        result = await PortfolioService(uow.session).backtest(
            allocs, capital=Decimal(str(body.capital)), start_ts=body.start, end_ts=body.end
        )
        await uow.rollback()  # backtests are throwaway

    return {
        "capital": result.capital,
        "equity": result.equity,
        "perf": result.perf,
        "legs": result.legs,
    }


async def _owned_alloc(
    registry: BotRegistry, bot_id: str, owner_id: str, weight: float
) -> Allocation:
    bot = await registry.get_bot(bot_id)
    if bot is None or bot.owner_id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bot not found: {bot_id}")
    versions = await registry.versions(bot_id)
    current = next((v for v in versions if v.version == bot.current_version), None)
    if current is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bot has no version: {bot_id}")
    return Allocation(bot=bot, version=current, weight=weight)


async def _subscribed_alloc(
    registry: BotRegistry,
    market: MarketplaceService,
    listing_id: str,
    subscribed: set[str],
    weight: float,
) -> Allocation:
    if listing_id not in subscribed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not subscribed to listing: {listing_id}")
    listing = await market.get(listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Listing not found: {listing_id}")
    bot = await registry.get_bot(listing.bot_id)
    if bot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing's bot is missing")
    versions = await registry.versions(listing.bot_id)
    # Run the exact version the subscriber follows (the listing's frozen version).
    version = next((v for v in versions if v.version == listing.bot_version), None)
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Listing's bot version is missing")
    return Allocation(bot=bot, version=version, weight=weight)

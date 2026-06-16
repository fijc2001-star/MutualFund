"""Subscriptions REST API (M-E over HTTP).

Any authenticated user can subscribe to an active listing (free is instant; paid records a
billing entry with the platform-fee split), list their subscriptions, replay the bot's signal
stream (entitlement-gated: only the subscriber can read it), and unsubscribe.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..foundation.uow import UnitOfWork
from ..iam.deps import CurrentPrincipal
from ..marketplace.service import MarketplaceService
from ..strategy.models import BotRegistry
from .service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscribeRequest(BaseModel):
    listing_id: str


class SubscriptionInfo(BaseModel):
    id: str
    listing_id: str
    symbol: str
    strategy_id: str
    started_at: str
    created_at: str


def _info(sub: Any) -> SubscriptionInfo:
    return SubscriptionInfo(
        id=sub.id,
        listing_id=sub.listing_id,
        symbol=sub.symbol,
        strategy_id=sub.strategy_id,
        started_at=sub.started_at.isoformat(),
        created_at=sub.created_at.isoformat(),
    )


@router.post("", response_model=SubscriptionInfo, status_code=status.HTTP_201_CREATED)
async def subscribe(body: SubscribeRequest, principal: CurrentPrincipal) -> SubscriptionInfo:
    async with UnitOfWork() as uow:
        market = MarketplaceService(uow.session)
        listing = await market.get(body.listing_id)
        if listing is None or listing.status != "active":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not available")
        # Resolve the listing's exact bot version → the definition we materialize.
        registry = BotRegistry(uow.session)
        versions = await registry.versions(listing.bot_id)
        version = next((v for v in versions if v.version == listing.bot_version), None)
        if version is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Listing's bot version is missing")
        sub = await SubscriptionService(uow.session).subscribe(
            listing, version.definition, subscriber=principal.user_id
        )
        await uow.commit()
        return _info(sub)


@router.get("", response_model=list[SubscriptionInfo])
async def my_subscriptions(principal: CurrentPrincipal) -> list[SubscriptionInfo]:
    async with UnitOfWork() as uow:
        subs = await SubscriptionService(uow.session).for_subscriber(principal.user_id)
    return [_info(s) for s in subs]


@router.get("/{subscription_id}/replay")
async def replay(subscription_id: str, principal: CurrentPrincipal) -> dict[str, Any]:
    async with UnitOfWork() as uow:
        svc = SubscriptionService(uow.session)
        sub = await svc.get(subscription_id)
        if sub is None or sub.subscriber != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
        candles, signals = await svc.replay(sub)
    return {"candles": candles, "signals": signals}


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(subscription_id: str, principal: CurrentPrincipal) -> None:
    async with UnitOfWork() as uow:
        svc = SubscriptionService(uow.session)
        sub = await svc.get(subscription_id)
        if sub is None or sub.subscriber != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
        await svc.unsubscribe(sub)
        await uow.commit()

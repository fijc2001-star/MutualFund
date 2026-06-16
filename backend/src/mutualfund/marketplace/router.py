"""Marketplace REST API (M-D over HTTP).

Any authenticated user can browse the catalog and view a listing's track record; only Designers
publish, and only the owning designer can change a listing's status. Tenancy is enforced by the
principal dependency (sets TenantContext).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..foundation.uow import UnitOfWork
from ..iam.deps import CurrentPrincipal, require_role
from ..iam.roles import Principal, Role
from ..strategy.models import BotRegistry
from .service import ListingError, MarketplaceService, listing_dict

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

DesignerPrincipal = Annotated[Principal, Depends(require_role(Role.DESIGNER))]


class PublishListingRequest(BaseModel):
    bot_id: str
    title: str
    description: str = ""
    price_cents: int = 0
    billing_period: str = "monthly"


class StatusRequest(BaseModel):
    status: str


class ListingInfo(BaseModel):
    id: str
    bot_id: str
    bot_version: int
    owner_id: str
    title: str
    description: str
    symbol: str
    strategy_id: str
    price_cents: int
    billing_period: str
    status: str
    track_record: dict[str, Any]
    created_at: str


@router.get("/listings", response_model=list[ListingInfo])
async def browse_listings(_: CurrentPrincipal) -> list[dict[str, Any]]:
    async with UnitOfWork() as uow:
        listings = await MarketplaceService(uow.session).list_active()
    return [listing_dict(listing) for listing in listings]


@router.get("/my-listings", response_model=list[ListingInfo])
async def my_listings(principal: DesignerPrincipal) -> list[dict[str, Any]]:
    async with UnitOfWork() as uow:
        listings = await MarketplaceService(uow.session).for_owner(principal.user_id)
    return [listing_dict(listing) for listing in listings]


@router.get("/listings/{listing_id}", response_model=ListingInfo)
async def get_listing(listing_id: str, _: CurrentPrincipal) -> dict[str, Any]:
    async with UnitOfWork() as uow:
        listing = await MarketplaceService(uow.session).get(listing_id)
        if listing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return listing_dict(listing)


@router.post("/listings", response_model=ListingInfo, status_code=status.HTTP_201_CREATED)
async def publish_listing(
    body: PublishListingRequest, principal: DesignerPrincipal
) -> dict[str, Any]:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.get_bot(body.bot_id)
        if bot is None or bot.owner_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
        versions = await registry.versions(bot.id)
        current = next((v for v in versions if v.version == bot.current_version), None)
        if current is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bot has no published version")
        try:
            listing = await MarketplaceService(uow.session).publish(
                bot,
                current,
                title=body.title,
                description=body.description,
                price_cents=body.price_cents,
                billing_period=body.billing_period,
            )
        except ListingError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        await uow.commit()
        return listing_dict(listing)


@router.post("/listings/{listing_id}/status", response_model=ListingInfo)
async def set_listing_status(
    listing_id: str, body: StatusRequest, principal: DesignerPrincipal
) -> dict[str, Any]:
    async with UnitOfWork() as uow:
        svc = MarketplaceService(uow.session)
        listing = await svc.get(listing_id)
        if listing is None or listing.owner_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
        try:
            listing = await svc.set_status(listing, body.status)
        except ListingError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        await uow.commit()
        return listing_dict(listing)

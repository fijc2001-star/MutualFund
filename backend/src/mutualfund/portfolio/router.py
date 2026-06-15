"""Portfolio REST API — backtest a weighted allocation across the designer's own bots."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..foundation.uow import UnitOfWork
from ..iam.deps import require_role
from ..iam.roles import Principal, Role
from ..strategy.models import BotRegistry
from .service import Allocation, PortfolioService

router = APIRouter(tags=["portfolio"])

DesignerPrincipal = Annotated[Principal, Depends(require_role(Role.DESIGNER))]


class AllocationItem(BaseModel):
    bot_id: str
    weight: float = 1.0


class PortfolioBacktestRequest(BaseModel):
    capital: float = 100_000.0
    start: int | None = None
    end: int | None = None
    allocations: list[AllocationItem]


@router.post("/portfolio/backtest")
async def portfolio_backtest(
    body: PortfolioBacktestRequest, principal: DesignerPrincipal
) -> dict[str, Any]:
    if not body.allocations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No allocations")

    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        allocs: list[Allocation] = []
        for item in body.allocations:
            bot = await registry.get_bot(item.bot_id)
            if bot is None or bot.owner_id != principal.user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bot not found: {item.bot_id}")
            versions = await registry.versions(item.bot_id)
            current = next((v for v in versions if v.version == bot.current_version), None)
            if current is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Bot has no version: {item.bot_id}"
                )
            allocs.append(Allocation(bot=bot, version=current, weight=item.weight))

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

"""Read-only market-data endpoints. Provider selected by config (REQUIREMENTS §6)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..config import get_settings
from ..foundation.instrument import AssetClass, Instrument
from ..iam.deps import CurrentPrincipal
from .provider import MarketDataProvider
from .providers.fake import FakeProvider
from .types import TimeFrame

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@lru_cache
def get_provider() -> MarketDataProvider:
    name = get_settings().marketdata_provider.lower()
    if name == "fake":
        return FakeProvider()
    if name == "schwab":
        from .providers.schwab import SchwabProvider

        return SchwabProvider()
    raise ValueError(f"Unknown market-data provider: {name}")


ProviderDep = Depends(get_provider)


class QuoteResponse(BaseModel):
    symbol: str
    bid: str
    ask: str
    last: str
    ts: datetime


class BarResponse(BaseModel):
    ts: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str


@router.get("/quote", response_model=QuoteResponse)
async def quote(
    principal: CurrentPrincipal,
    symbol: str = Query(...),
    provider: MarketDataProvider = ProviderDep,
) -> QuoteResponse:
    q = await provider.quote(Instrument(symbol=symbol, asset_class=AssetClass.EQUITY))
    return QuoteResponse(
        symbol=symbol, bid=str(q.bid), ask=str(q.ask), last=str(q.last), ts=q.ts
    )


@router.get("/bars", response_model=list[BarResponse])
async def bars(
    principal: CurrentPrincipal,
    symbol: str = Query(...),
    timeframe: TimeFrame = Query(TimeFrame.D1),
    days: int = Query(30, ge=1, le=365),
    provider: MarketDataProvider = ProviderDep,
) -> list[BarResponse]:
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    rows = await provider.bars(
        Instrument(symbol=symbol, asset_class=AssetClass.EQUITY), timeframe, start, end
    )
    return [
        BarResponse(
            ts=b.ts,
            open=str(b.open),
            high=str(b.high),
            low=str(b.low),
            close=str(b.close),
            volume=str(b.volume),
        )
        for b in rows
    ]


@router.get("/options/chain")
async def option_chain(
    principal: CurrentPrincipal,
    underlying: str = Query(...),
    expiry: date | None = Query(None),
    provider: MarketDataProvider = ProviderDep,
) -> dict[str, object]:
    chain = await provider.option_chain(underlying, expiry)
    return {
        "underlying": chain.underlying,
        "contracts": [
            {
                "symbol": c.instrument.symbol,
                "expiry": c.instrument.expiry.isoformat() if c.instrument.expiry else None,
                "strike": str(c.instrument.strike),
                "option_type": c.instrument.option_type,
                "bid": str(c.bid),
                "ask": str(c.ask),
                "last": str(c.last),
            }
            for c in chain.contracts
        ],
    }

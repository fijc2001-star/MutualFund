"""ThinkorSwim / Schwab market-data adapter (REQUIREMENTS §6).

TD Ameritrade's API migrated to the Schwab Developer API. This adapter speaks the
same MarketDataProvider interface as everything else, so it is swappable via config.

NOTE: requires Schwab app registration/approval. Until credentials exist, run with
MARKETDATA_PROVIDER=fake. Endpoint paths/fields below follow the documented Schwab
Market Data API shape and may need tuning against the live API.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from ...config import get_settings
from ...foundation.instrument import AssetClass, Instrument
from ..types import Bar, OptionChain, OptionContract, Quote, TimeFrame

_TF_TO_SCHWAB: dict[TimeFrame, tuple[str, int]] = {
    # (frequencyType, frequency)
    TimeFrame.M1: ("minute", 1),
    TimeFrame.M5: ("minute", 5),
    TimeFrame.M15: ("minute", 15),
    TimeFrame.H1: ("minute", 60),
    TimeFrame.D1: ("daily", 1),
}


class SchwabAuth:
    """Holds and refreshes the Schwab OAuth access token (app-level, not user auth)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token
        settings = get_settings()
        if not (
            settings.schwab_client_id
            and settings.schwab_client_secret
            and settings.schwab_refresh_token
        ):
            raise RuntimeError("Schwab credentials are not configured")
        resp = await self._client.post(
            settings.schwab_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": settings.schwab_refresh_token,
            },
            auth=(settings.schwab_client_id, settings.schwab_client_secret),
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 1800))
        assert self._access_token is not None
        return self._access_token


class SchwabProvider:
    name = "schwab"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=get_settings().schwab_api_base)
        self._auth = SchwabAuth(self._client)

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._auth.token()}"}

    async def quote(self, instrument: Instrument) -> Quote:
        resp = await self._client.get(
            "/marketdata/v1/quotes",
            params={"symbols": instrument.symbol},
            headers=await self._headers(),
        )
        resp.raise_for_status()
        payload = resp.json()[instrument.symbol]["quote"]
        return Quote(
            instrument=instrument,
            bid=Decimal(str(payload["bidPrice"])),
            ask=Decimal(str(payload["askPrice"])),
            last=Decimal(str(payload["lastPrice"])),
            ts=datetime.now(UTC),
        )

    async def bars(
        self, instrument: Instrument, timeframe: TimeFrame, start: datetime, end: datetime
    ) -> list[Bar]:
        freq_type, freq = _TF_TO_SCHWAB[timeframe]
        resp = await self._client.get(
            "/marketdata/v1/pricehistory",
            params={
                "symbol": instrument.symbol,
                "frequencyType": freq_type,
                "frequency": freq,
                "startDate": int(start.timestamp() * 1000),
                "endDate": int(end.timestamp() * 1000),
            },
            headers=await self._headers(),
        )
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        return [
            Bar(
                instrument=instrument,
                ts=datetime.fromtimestamp(c["datetime"] / 1000, tz=UTC),
                open=Decimal(str(c["open"])),
                high=Decimal(str(c["high"])),
                low=Decimal(str(c["low"])),
                close=Decimal(str(c["close"])),
                volume=Decimal(str(c["volume"])),
            )
            for c in candles
        ]

    async def option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> OptionChain:
        params: dict[str, str] = {"symbol": underlying}
        if expiry is not None:
            params["fromDate"] = expiry.isoformat()
            params["toDate"] = expiry.isoformat()
        resp = await self._client.get(
            "/marketdata/v1/chains", params=params, headers=await self._headers()
        )
        resp.raise_for_status()
        data = resp.json()
        contracts: list[OptionContract] = []
        for map_key in ("callExpDateMap", "putExpDateMap"):
            opt_type = "C" if map_key.startswith("call") else "P"
            for _exp, strikes in data.get(map_key, {}).items():
                for strike_str, entries in strikes.items():
                    for entry in entries:
                        exp_dt = datetime.fromtimestamp(
                            entry["expirationDate"] / 1000, tz=UTC
                        ).date()
                        ins = Instrument(
                            symbol=underlying,
                            asset_class=AssetClass.OPTION,
                            expiry=exp_dt,
                            strike=Decimal(strike_str),
                            option_type=opt_type,  # type: ignore[arg-type]
                            multiplier=Decimal(str(entry.get("multiplier", 100))),
                        )
                        contracts.append(
                            OptionContract(
                                instrument=ins,
                                bid=Decimal(str(entry["bid"])),
                                ask=Decimal(str(entry["ask"])),
                                last=Decimal(str(entry["last"])),
                                implied_volatility=(
                                    Decimal(str(entry["volatility"]))
                                    if entry.get("volatility") is not None
                                    else None
                                ),
                                delta=(
                                    Decimal(str(entry["delta"]))
                                    if entry.get("delta") is not None
                                    else None
                                ),
                            )
                        )
        return OptionChain(underlying=underlying, contracts=contracts)

    async def stream(self, instruments: list[Instrument]) -> AsyncIterator[Quote]:
        # Realtime streaming uses Schwab's websocket API — implemented later.
        raise NotImplementedError("Schwab realtime streaming not yet implemented")
        yield  # pragma: no cover  (makes this an async generator)

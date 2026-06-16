"""WebSocket endpoint streaming fake bars + signals for the chart prototype.

Protocol (JSON messages):
  {"type": "snapshot", "symbol": "AAPL", "bars": [DemoBar, ...]}
  {"type": "bar", "bar": DemoBar}
  {"type": "signal", "signal": DemoSignal}
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..backtest.service import BacktestService
from ..config import get_settings
from ..foundation.ids import TenantId
from ..foundation.tenant import TenantContext
from ..foundation.uow import UnitOfWork
from ..strategy.strategy import BotDefinition
from ..subscription.models import Subscription
from ..subscription.service import SubscriptionService
from .demo import DemoFeed, bar_dict, signal_dict
from .sandbox_session import SandboxSession

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/demo")
async def demo_signals(websocket: WebSocket) -> None:
    await websocket.accept()
    symbol = websocket.query_params.get("symbol", "AAPL")
    try:
        interval = float(websocket.query_params.get("interval", "1.0"))
    except ValueError:
        interval = 1.0

    feed = DemoFeed(symbol)
    # Seed the chart with history.
    history = feed.snapshot(60)
    await websocket.send_json(
        {"type": "snapshot", "symbol": symbol, "bars": [bar_dict(b) for b in history]}
    )

    try:
        while True:
            await asyncio.sleep(interval)
            bar = feed.next_bar()
            await websocket.send_json({"type": "bar", "bar": bar_dict(bar)})
            signal = feed.maybe_signal(bar)
            if signal is not None:
                await websocket.send_json(
                    {"type": "signal", "signal": signal_dict(signal)}
                )
    except WebSocketDisconnect:
        return
    except (asyncio.CancelledError, RuntimeError):
        with contextlib.suppress(RuntimeError):
            await websocket.close()


@router.websocket("/ws/sandbox")
async def sandbox_stream(websocket: WebSocket) -> None:
    """Live chart driven by the REAL M5 sandbox + M10 ledger (SMA-cross demo strategy)."""
    await websocket.accept()
    symbol = websocket.query_params.get("symbol", "AAPL")
    try:
        interval = float(websocket.query_params.get("interval", "1.0"))
    except ValueError:
        interval = 1.0

    settings = get_settings()
    token = TenantContext.set(TenantId(settings.default_tenant_id))
    try:
        async with UnitOfWork() as uow:
            session = SandboxSession(uow, symbol, settings.sandbox_starting_cash)
            await session.run(websocket.send_json, interval=interval)
    except WebSocketDisconnect:
        return
    except (asyncio.CancelledError, RuntimeError):
        with contextlib.suppress(RuntimeError):
            await websocket.close()
    finally:
        TenantContext.reset(token)


@router.get("/backtest")
async def backtest_window(
    symbol: str = "AAPL", start: int | None = None, end: int | None = None
) -> dict[str, Any]:
    """Backtest a bot over an optional [start, end] window (unix seconds).

    Returns the window's candles, executed signals, per-bar equity curve, and performance —
    everything the client needs to play the period back bar by bar. Runs in a rolled-back
    unit of work, so it persists nothing.
    """
    settings = get_settings()
    token = TenantContext.set(TenantId(settings.default_tenant_id))
    try:
        async with UnitOfWork() as uow:
            result = await BacktestService(uow.session).run(symbol, start_ts=start, end_ts=end)
            await uow.rollback()
        return {
            "symbol": symbol,
            "start": result.start,
            "end": result.end,
            "bars": result.bars,
            "signals": result.signals,
            "equity": result.equity,
            "perf": result.perf,
        }
    finally:
        TenantContext.reset(token)


@router.websocket("/ws/replay")
async def replay_stream(websocket: WebSocket) -> None:
    """Replay a bot's persisted signal stream since the subscription started.

    Reads the bot's hash-chained SIGNAL events from the ledger (not a live recomputation)
    and streams the candle history + every signal so the client can scrub the full record.
    """
    await websocket.accept()
    symbol = websocket.query_params.get("symbol", "AAPL")

    settings = get_settings()
    token = TenantContext.set(TenantId(settings.default_tenant_id))
    try:
        async with UnitOfWork() as uow:
            svc = SubscriptionService(uow.session)
            stream_id = f"bot:demo:{symbol}"
            definition = BotDefinition("sma_cross", {"fast": 9, "slow": 21}, (symbol,))
            await svc.materialize_stream(stream_id, symbol, definition)
            # A transient (un-persisted) window over the shared stream from the beginning.
            sub = Subscription(
                subscriber="demo",
                listing_id="demo",
                symbol=symbol,
                strategy_id="sma_cross",
                stream_id=stream_id,
                started_at=datetime.fromtimestamp(0, UTC),
                created_at=datetime.now(UTC),
            )
            bars, signals = await svc.replay(sub)
            await uow.commit()  # persist the materialized signal stream

        # Backtest the bot over its history for the equity curve + stats. Runs in its own
        # unit of work that we roll back, so the throwaway fills never persist.
        async with UnitOfWork() as bt_uow:
            result = await BacktestService(bt_uow.session).run(symbol)
            await bt_uow.rollback()

        await websocket.send_json({"type": "snapshot", "symbol": symbol, "bars": bars})
        await websocket.send_json({"type": "perf", "perf": result.perf})
        await websocket.send_json({"type": "equity", "equity": result.equity})
        for signal in signals:
            await websocket.send_json({"type": "signal", "signal": signal})
        await websocket.send_json(
            {
                "type": "replay_done",
                "count": len(signals),
                "since": int(sub.started_at.timestamp()),
            }
        )
        await websocket.close()
    except WebSocketDisconnect:
        return
    except (asyncio.CancelledError, RuntimeError):
        with contextlib.suppress(RuntimeError):
            await websocket.close()
    finally:
        TenantContext.reset(token)

"""WebSocket endpoint streaming fake bars + signals for the chart prototype.

Protocol (JSON messages):
  {"type": "snapshot", "symbol": "AAPL", "bars": [DemoBar, ...]}
  {"type": "bar", "bar": DemoBar}
  {"type": "signal", "signal": DemoSignal}
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .demo import DemoFeed, bar_dict, signal_dict

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

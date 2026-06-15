"""The agentic strategy gates SMA-cross candidates through a pluggable LLM client.

These tests use the deterministic stub (and a fake client) — no network, no API key — so they
mirror how backtests/qualification run the agent today.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.signals.signal import Action
from mutualfund.strategy.library.agent import (
    AgentDecision,
    AgentParams,
    AgentStrategy,
    AgentView,
    StubLLMClient,
)
from mutualfund.strategy.registry import default_registry
from mutualfund.strategy.strategy import Strategy, StrategyContext

AAPL = Instrument("AAPL", AssetClass.EQUITY)


def _replay(strategy: Strategy, closes: list[float]) -> list[Action]:
    """Stream closes one bar at a time, applying fills so position gating is exercised."""
    actions: list[Action] = []
    position = Decimal(0)
    for i in range(1, len(closes) + 1):
        ctx = StrategyContext(AAPL, closes[:i], position=position)
        signals = strategy.evaluate(ctx)
        for sig in signals:
            actions.append(sig.action)
            position += Decimal(100) if sig.action is Action.BUY else Decimal(-100)
    return actions


class _AlwaysHold:
    def decide(self, view: AgentView) -> AgentDecision:
        return AgentDecision("hold", thesis="standing down")


class _RecordingConfirm:
    """Confirms whatever candidate is proposed and records the views it saw."""

    def __init__(self) -> None:
        self.seen: list[AgentView] = []

    def decide(self, view: AgentView) -> AgentDecision:
        self.seen.append(view)
        return AgentDecision(view.candidate, thesis="confirmed", invalidation="trend reverses")


def test_agent_confirms_candidates_and_alternates() -> None:
    strategy = AgentStrategy(
        fast=3, slow=6, rsi_len=5, style="balanced", client=_RecordingConfirm()
    )
    closes = (
        [10.0] * 6
        + [11.0, 12.0, 13.0, 14.0, 15.0, 16.0]  # ramp up -> cross above
        + [15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0]  # ramp down -> cross below
    )
    actions = _replay(strategy, closes)
    assert actions[0] is Action.BUY
    assert Action.SELL in actions
    # No double-entry / double-exit: actions strictly alternate.
    assert all(a != b for a, b in zip(actions, actions[1:], strict=False))


def test_agent_veto_suppresses_all_trades() -> None:
    strategy = AgentStrategy(fast=3, slow=6, rsi_len=5, style="balanced", client=_AlwaysHold())
    closes = [10.0] * 6 + [11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    assert _replay(strategy, closes) == []


def test_agent_signal_carries_agent_rationale() -> None:
    client = _RecordingConfirm()
    strategy = AgentStrategy(fast=2, slow=4, rsi_len=3, style="aggressive", client=client)
    closes = [10.0, 10.0, 10.0, 10.0, 11.0, 12.0, 13.0]
    signals = [
        s
        for i in range(1, len(closes) + 1)
        for s in strategy.evaluate(StrategyContext(AAPL, closes[:i]))
    ]
    assert signals, "expected a confirmed crossing signal"
    rationale = signals[0].rationale
    assert rationale is not None
    assert rationale.thesis == "confirmed"
    assert any(ind.startswith("RSI(") for ind in rationale.indicators)
    # The agent saw the style and the proposed side.
    assert client.seen[0].style == "aggressive"
    assert client.seen[0].candidate == "buy"


def test_stub_client_vetoes_overbought_buys() -> None:
    stub = StubLLMClient()
    overbought = AgentView(
        symbol="AAPL", candidate="buy", fast=12.0, slow=10.0, rsi=82.0,
        recent_closes=(10.0, 11.0, 12.0), position=0.0, style="balanced",
    )
    assert stub.decide(overbought).action == "hold"
    healthy = AgentView(
        symbol="AAPL", candidate="buy", fast=12.0, slow=10.0, rsi=55.0,
        recent_closes=(10.0, 11.0, 12.0), position=0.0, style="balanced",
    )
    assert stub.decide(healthy).action == "buy"


def test_agent_registered_and_buildable() -> None:
    assert "agent" in default_registry.ids()
    strategy = default_registry.build("agent", {"fast": 5, "slow": 20})
    assert isinstance(strategy, Strategy)


def test_agent_params_reject_fast_not_below_slow() -> None:
    with pytest.raises(ValidationError):
        AgentParams(fast=10, slow=5)

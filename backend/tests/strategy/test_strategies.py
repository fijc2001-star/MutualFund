"""Concrete strategies evaluate deterministically and respect position gating."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.signals.signal import Action
from mutualfund.strategy.library.momentum import MomentumParams, MomentumStrategy
from mutualfund.strategy.library.sma_cross import SmaCrossParams, SmaCrossStrategy
from mutualfund.strategy.strategy import Strategy, StrategyContext

AAPL = Instrument("AAPL", AssetClass.EQUITY)


def _replay(strategy: Strategy, closes: list[float]) -> list[Action]:
    """Stream `closes` one bar at a time, applying fills, and collect the actions taken.

    Mirrors how the sandbox runs a strategy: position grows/shrinks as orders fill, which
    feeds back into the next context — so position gating is exercised end to end.
    """
    actions: list[Action] = []
    position = Decimal(0)
    for i in range(1, len(closes) + 1):
        ctx = StrategyContext(AAPL, closes[:i], position=position)
        signals = strategy.evaluate(ctx)
        # Determinism: same context, same result.
        assert [s.action for s in strategy.evaluate(ctx)] == [s.action for s in signals]
        for sig in signals:
            actions.append(sig.action)
            position += Decimal(100) if sig.action is Action.BUY else Decimal(-100)
    return actions


def test_sma_cross_buys_up_sells_down_once_each() -> None:
    strategy = SmaCrossStrategy(fast=3, slow=6)
    closes = (
        [10.0] * 6  # flat: no crossing
        + [11.0, 12.0, 13.0, 14.0, 15.0, 16.0]  # ramp up -> fast crosses above slow
        + [15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0]  # ramp down -> fast crosses below
    )
    actions = _replay(strategy, closes)

    assert Action.BUY in actions
    assert Action.SELL in actions
    # No double-entry / double-exit: actions strictly alternate, starting with a BUY.
    assert actions[0] is Action.BUY
    assert all(a != b for a, b in zip(actions, actions[1:], strict=False))


def test_sma_cross_emits_rationale() -> None:
    strategy = SmaCrossStrategy(fast=2, slow=4)
    closes = [10.0, 10.0, 10.0, 10.0, 11.0, 12.0]
    signals = [s for i in range(1, len(closes) + 1)
               for s in strategy.evaluate(StrategyContext(AAPL, closes[:i]))]
    assert signals, "expected at least one crossing signal"
    rationale = signals[0].rationale
    assert rationale is not None
    assert rationale.indicators
    assert rationale.invalidation


def test_sma_cross_params_reject_fast_not_below_slow() -> None:
    with pytest.raises(ValidationError):
        SmaCrossParams(fast=10, slow=5)
    with pytest.raises(ValidationError):
        SmaCrossParams(fast=5, slow=5)
    with pytest.raises(ValidationError):
        SmaCrossParams(fast=0, slow=5)


def test_momentum_buys_on_positive_then_sells_on_reversal() -> None:
    strategy = MomentumStrategy(lookback=3, threshold=0.0)
    closes = [10.0, 10.0, 10.0, 11.0, 12.0, 13.0, 12.0, 10.0, 8.0, 6.0]
    actions = _replay(strategy, closes)
    assert actions[0] is Action.BUY
    assert Action.SELL in actions


def test_momentum_threshold_suppresses_small_moves() -> None:
    strategy = MomentumStrategy(lookback=2, threshold=0.5)  # need +50% to fire
    closes = [10.0, 10.0, 10.1, 10.2, 10.3]  # tiny drift, never clears threshold
    assert _replay(strategy, closes) == []


def test_momentum_params_reject_bad_values() -> None:
    with pytest.raises(ValidationError):
        MomentumParams(lookback=0)
    with pytest.raises(ValidationError):
        MomentumParams(threshold=-0.1)

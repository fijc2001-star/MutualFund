"""The signal engine runs a BotDefinition through the registry to produce signals."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.signals.engine import SignalEngine
from mutualfund.signals.signal import Action
from mutualfund.strategy.registry import UnknownStrategyError
from mutualfund.strategy.strategy import BotDefinition, StrategyContext

AAPL = Instrument("AAPL", AssetClass.EQUITY)


def test_engine_runs_definition_into_signals() -> None:
    engine = SignalEngine()
    definition = BotDefinition("sma_cross", {"fast": 2, "slow": 4})
    # Flat then a jump on the last bar: fast SMA crosses above slow exactly here.
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0]
    signals = engine.run(definition, StrategyContext(AAPL, closes, position=Decimal(0)))
    assert [s.action for s in signals] == [Action.BUY]


def test_engine_respects_position_from_context() -> None:
    engine = SignalEngine()
    definition = BotDefinition("sma_cross", {"fast": 2, "slow": 4})
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0]
    # Already long: the up-cross should not re-enter.
    signals = engine.run(definition, StrategyContext(AAPL, closes, position=Decimal(100)))
    assert signals == []


def test_engine_unknown_strategy_raises() -> None:
    engine = SignalEngine()
    with pytest.raises(UnknownStrategyError):
        engine.run(BotDefinition("nope", {}), StrategyContext(AAPL, [1.0, 2.0]))


def test_engine_validates_params() -> None:
    engine = SignalEngine()
    with pytest.raises(ValidationError):
        engine.run(BotDefinition("sma_cross", {"fast": 30, "slow": 5}), StrategyContext(AAPL, []))

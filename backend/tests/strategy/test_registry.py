"""The strategy registry resolves ids, validates params, and builds strategies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mutualfund.strategy.registry import (
    StrategyRegistry,
    UnknownStrategyError,
    default_registry,
)
from mutualfund.strategy.strategy import Strategy


def test_default_registry_has_builtin_strategies() -> None:
    assert {"sma_cross", "momentum"} <= set(default_registry.ids())


def test_get_unknown_strategy_raises() -> None:
    with pytest.raises(UnknownStrategyError):
        default_registry.get("does_not_exist")


def test_build_validates_and_constructs() -> None:
    strategy = default_registry.build("sma_cross", {"fast": 5, "slow": 20})
    assert isinstance(strategy, Strategy)


def test_build_rejects_bad_params() -> None:
    with pytest.raises(ValidationError):
        default_registry.build("sma_cross", {"fast": 30, "slow": 5})


def test_validate_fills_defaults() -> None:
    params = default_registry.validate("sma_cross", {})
    assert params.model_dump() == {"fast": 9, "slow": 21}


def test_register_is_isolated_per_registry() -> None:
    registry = StrategyRegistry()
    assert registry.ids() == []
    with pytest.raises(UnknownStrategyError):
        registry.build("sma_cross", {})

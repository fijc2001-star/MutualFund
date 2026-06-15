"""Strategy registry: resolve a `strategy_id` to its class, validate raw params against the
strategy's schema, and build a ready-to-evaluate `Strategy`. Bots reference strategies by id
(see `strategy.models.BotVersion`), so this is the single seam where untrusted params are
validated before a bot can run or publish.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from .library import AgentStrategy, MomentumStrategy, SmaCrossStrategy
from .strategy import RegisteredStrategy, Strategy


class UnknownStrategyError(KeyError):
    """Raised when a `strategy_id` has no registered strategy."""


class StrategyRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, type[RegisteredStrategy]] = {}

    def register(self, strategy_cls: type[RegisteredStrategy]) -> type[RegisteredStrategy]:
        self._by_id[strategy_cls.strategy_id] = strategy_cls
        return strategy_cls

    def get(self, strategy_id: str) -> type[RegisteredStrategy]:
        try:
            return self._by_id[strategy_id]
        except KeyError as exc:
            raise UnknownStrategyError(strategy_id) from exc

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def validate(self, strategy_id: str, params: Mapping[str, Any]) -> BaseModel:
        """Validate raw params against the strategy's schema; raises on bad params."""
        return self.get(strategy_id).params_model.model_validate(dict(params))

    def build(self, strategy_id: str, params: Mapping[str, Any]) -> Strategy:
        """Validate params and construct the strategy."""
        cls = self.get(strategy_id)
        return cls.build(self.validate(strategy_id, params))


def _default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(SmaCrossStrategy)
    registry.register(MomentumStrategy)
    registry.register(AgentStrategy)
    return registry


default_registry = _default_registry()

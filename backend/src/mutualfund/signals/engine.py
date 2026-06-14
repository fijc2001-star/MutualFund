"""The signal engine: run a bot definition against a market context to produce signals.

`run` instantiates the bot's `Strategy` from its (already-frozen) params via the registry and
evaluates it. Strategies are stateless, so a definition + context fully determine the output —
the engine holds no per-bot state between ticks.
"""

from __future__ import annotations

from ..strategy.registry import StrategyRegistry, default_registry
from ..strategy.strategy import BotDefinition, StrategyContext
from .signal import Signal


class SignalEngine:
    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or default_registry

    def run(self, definition: BotDefinition, ctx: StrategyContext) -> list[Signal]:
        strategy = self._registry.build(definition.strategy_id, definition.params)
        return strategy.evaluate(ctx)

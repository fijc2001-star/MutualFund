"""Strategy building blocks: the evaluation contract + the context it sees.

A `Strategy` turns a `StrategyContext` (recent prices + current position for one
instrument) into a list of `Signal`s. `RegisteredStrategy` adds the metadata a bot needs
to *reference* a strategy by id and validate its params on publish (REQUIREMENTS §5.8.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel

from ..foundation.instrument import Instrument
from ..signals.signal import Signal


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """What a strategy sees for one instrument at one point in time.

    `closes` are recent closing prices, oldest → newest. `position` is the current signed
    position quantity (0 when flat), so a strategy can avoid re-entering or know to exit.
    """

    instrument: Instrument
    closes: Sequence[float]
    position: Decimal = Decimal(0)

    def sma(self, n: int, *, offset: int = 0) -> float | None:
        """Simple moving average of the last `n` closes, ending `offset` bars back.

        Returns None when there aren't enough closes for the requested window.
        """
        end = len(self.closes) - offset
        if n <= 0 or end < n:
            return None
        return sum(self.closes[end - n : end]) / n


@dataclass(frozen=True, slots=True)
class BotDefinition:
    """An immutable, runnable spec: which strategy, its frozen params, and the universe.

    This is the value-object form of a stored `BotVersion` (see `strategy.models`) — the
    thing `SignalEngine` actually runs. Keeping it ORM-free lets the engine and the live
    sandbox build a definition without touching the database.
    """

    strategy_id: str
    params: Mapping[str, Any] = field(default_factory=dict)
    universe: tuple[str, ...] = ()


@runtime_checkable
class Strategy(Protocol):
    """The minimal evaluation contract every strategy implementation satisfies."""

    def evaluate(self, ctx: StrategyContext) -> list[Signal]: ...


class RegisteredStrategy(ABC):
    """A strategy that can be referenced by id in a `BotVersion` and validated on publish.

    Subclasses declare a stable `strategy_id` and a pydantic `params_model`; the registry
    validates raw params against that model and constructs the strategy via `build`.
    """

    strategy_id: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]

    @classmethod
    @abstractmethod
    def build(cls, params: BaseModel) -> Strategy:
        """Construct a ready-to-evaluate strategy from validated params."""

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> list[Signal]: ...

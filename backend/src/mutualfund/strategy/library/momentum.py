"""Time-series momentum: go long when the lookback return clears a threshold, exit when it
turns negative past the threshold. Level-based (not crossing-based) but still deterministic:
position gating keeps it from re-entering, so a given context yields at most one signal.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...signals.signal import Action, Rationale, Signal
from ..strategy import RegisteredStrategy, Strategy, StrategyContext


class MomentumParams(BaseModel):
    """`lookback` bars of return; `threshold` is the absolute return band (e.g. 0.02 = 2%)."""

    lookback: int = Field(default=20, gt=0)
    threshold: float = Field(default=0.0, ge=0.0)


class MomentumStrategy(RegisteredStrategy):
    strategy_id = "momentum"
    params_model = MomentumParams

    def __init__(self, lookback: int, threshold: float) -> None:
        self._lookback = lookback
        self._threshold = threshold

    @classmethod
    def build(cls, params: BaseModel) -> Strategy:
        assert isinstance(params, MomentumParams)
        return cls(params.lookback, params.threshold)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        if len(ctx.closes) <= self._lookback:
            return []
        past = ctx.closes[-1 - self._lookback]
        if past == 0:
            return []
        ret = ctx.closes[-1] / past - 1.0
        indicators = [f"return({self._lookback})={ret:.4%}"]

        if ret > self._threshold and ctx.position <= 0:
            return [
                Signal(
                    ctx.instrument,
                    Action.BUY,
                    Decimal(1),
                    Rationale(
                        thesis=f"{self._lookback}-bar momentum is positive ({ret:.2%})",
                        indicators=indicators,
                        invalidation="momentum falls below the threshold",
                    ),
                )
            ]
        if ret < -self._threshold and ctx.position > 0:
            return [
                Signal(
                    ctx.instrument,
                    Action.SELL,
                    Decimal(1),
                    Rationale(
                        thesis=f"{self._lookback}-bar momentum turned negative ({ret:.2%})",
                        indicators=indicators,
                        invalidation="momentum rises back above the threshold",
                    ),
                )
            ]
        return []

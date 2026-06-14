"""SMA-crossover strategy: go long when the fast SMA crosses above the slow SMA.

A faithful, *stateless* port of the Phase-2 chart demo. Crossing is detected by comparing
this bar's SMA gap against the previous bar's (via `StrategyContext.sma(offset=1)`), so the
same context always yields the same signal — no hidden instance state to replay.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from ...signals.signal import Action, Rationale, Signal
from ..strategy import RegisteredStrategy, Strategy, StrategyContext


class SmaCrossParams(BaseModel):
    """Fast/slow window lengths; `fast` must be strictly shorter than `slow`."""

    fast: int = Field(default=9, gt=0)
    slow: int = Field(default=21, gt=0)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> SmaCrossParams:
        if self.fast >= self.slow:
            raise ValueError("fast window must be shorter than slow window")
        return self


class SmaCrossStrategy(RegisteredStrategy):
    strategy_id = "sma_cross"
    params_model = SmaCrossParams

    def __init__(self, fast: int, slow: int) -> None:
        self._fast = fast
        self._slow = slow

    @classmethod
    def build(cls, params: BaseModel) -> Strategy:
        assert isinstance(params, SmaCrossParams)
        return cls(params.fast, params.slow)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        fast = ctx.sma(self._fast)
        slow = ctx.sma(self._slow)
        prev_fast = ctx.sma(self._fast, offset=1)
        prev_slow = ctx.sma(self._slow, offset=1)
        if fast is None or slow is None or prev_fast is None or prev_slow is None:
            return []

        crossed_up = prev_fast <= prev_slow and fast > slow
        crossed_down = prev_fast >= prev_slow and fast < slow
        indicators = [f"SMA({self._fast})={fast:.4f}", f"SMA({self._slow})={slow:.4f}"]

        if crossed_up and ctx.position <= 0:
            return [
                Signal(
                    ctx.instrument,
                    Action.BUY,
                    Decimal(1),
                    Rationale(
                        thesis=f"Fast SMA({self._fast}) crossed above slow SMA({self._slow})",
                        indicators=indicators,
                        invalidation="fast SMA falls back below slow SMA",
                    ),
                )
            ]
        if crossed_down and ctx.position > 0:
            return [
                Signal(
                    ctx.instrument,
                    Action.SELL,
                    Decimal(1),
                    Rationale(
                        thesis=f"Fast SMA({self._fast}) crossed below slow SMA({self._slow})",
                        indicators=indicators,
                        invalidation="fast SMA rises back above slow SMA",
                    ),
                )
            ]
        return []

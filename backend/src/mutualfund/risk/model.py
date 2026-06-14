"""RiskModel: approve or reject an order against portfolio concentration/leverage limits.

This is the per-order gate between sizing and execution. It looks at the *projected*
portfolio (current positions + this order) so a fill can never push a name over its
weight cap or the book over its options-leverage cap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..execution.orders import Order, Position, Side
from ..foundation.instrument import AssetClass


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_position_pct: Decimal = Decimal("0.25")  # max single-name weight of equity
    max_options_leverage: Decimal = Decimal("1.0")  # total options notional / equity


@dataclass(frozen=True, slots=True)
class PortfolioState:
    equity: Decimal
    positions: Sequence[Position]
    marks: Mapping[str, Decimal]  # instrument.key -> current price (incl. the order's)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str | None = None


class RiskModel:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()

    def check(self, order: Order, portfolio: PortfolioState) -> RiskDecision:
        if portfolio.equity <= 0:
            return RiskDecision(False, "non-positive equity")

        key = order.instrument.key
        current = next(
            (p.quantity for p in portfolio.positions if p.instrument.key == key), Decimal(0)
        )
        delta = order.quantity if order.side is Side.BUY else -order.quantity
        projected = current + delta
        price = portfolio.marks.get(key, Decimal(0))
        mult = order.instrument.multiplier
        position_value = abs(projected) * price * mult

        weight = position_value / portfolio.equity
        if weight > self._limits.max_position_pct:
            return RiskDecision(
                False,
                f"name weight {weight:.1%} exceeds max {self._limits.max_position_pct:.1%}",
            )

        options_notional = Decimal(0)
        for pos in portfolio.positions:
            if pos.instrument.asset_class is AssetClass.OPTION and pos.instrument.key != key:
                mark = portfolio.marks.get(pos.instrument.key, Decimal(0))
                options_notional += abs(pos.quantity) * mark * pos.instrument.multiplier
        if order.instrument.asset_class is AssetClass.OPTION:
            options_notional += position_value
        leverage = options_notional / portfolio.equity
        if leverage > self._limits.max_options_leverage:
            return RiskDecision(
                False,
                f"options leverage {leverage:.2f}x exceeds max "
                f"{self._limits.max_options_leverage:.2f}x",
            )

        return RiskDecision(True)

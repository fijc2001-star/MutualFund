"""CommissionModel — broker fees. Equities (often $0) + per-contract options fees."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from ...foundation.instrument import AssetClass
from ..orders import Order


class CommissionModel(Protocol):
    def fee(self, order: Order, fill_price: Decimal) -> Decimal: ...


class StandardCommission:
    def __init__(
        self,
        equity_per_share: Decimal = Decimal(0),
        option_per_contract: Decimal = Decimal("0.65"),
    ) -> None:
        self._equity_per_share = equity_per_share
        self._option_per_contract = option_per_contract

    def fee(self, order: Order, fill_price: Decimal) -> Decimal:
        if order.instrument.asset_class is AssetClass.OPTION:
            return self._option_per_contract * order.quantity
        return self._equity_per_share * order.quantity

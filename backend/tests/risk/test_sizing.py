"""Position sizers compute the right quantities and flatten on exits."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.risk.sizing import (
    FixedFractional,
    FixedQuantity,
    SizingContext,
    VolatilityTarget,
)
from mutualfund.signals.signal import Action, Rationale, Signal

AAPL = Instrument("AAPL", AssetClass.EQUITY)


def _signal(action: Action, strength: Decimal = Decimal(1)) -> Signal:
    return Signal(AAPL, action, strength, Rationale("t"))


def _ctx(price: str = "100", equity: str = "100000", position: str = "0",
         closes: list[float] | None = None) -> SizingContext:
    return SizingContext(
        AAPL, Decimal(price), Decimal(equity), Decimal(position), closes or []
    )


def test_fixed_quantity_entry() -> None:
    sizer = FixedQuantity(Decimal(50))
    assert sizer.quantity(_signal(Action.BUY), _ctx()) == Decimal(50)


def test_fixed_fractional_floors_to_whole_shares() -> None:
    # 10% of 100k = 10,000 / 100 = 100 shares.
    sizer = FixedFractional(Decimal("0.10"))
    assert sizer.quantity(_signal(Action.BUY), _ctx(price="100")) == Decimal(100)
    # 10% of 100k = 10,000 / 99 = 101.01 -> floored to 101.
    assert sizer.quantity(_signal(Action.BUY), _ctx(price="99")) == Decimal(101)


def test_strength_scales_entry() -> None:
    sizer = FixedFractional(Decimal("0.10"))
    qty = sizer.quantity(_signal(Action.BUY, Decimal("0.5")), _ctx(price="100"))
    assert qty == Decimal(50)


def test_exit_flattens_current_position() -> None:
    sizer = FixedFractional(Decimal("0.10"))
    assert sizer.quantity(_signal(Action.SELL), _ctx(position="73")) == Decimal(73)
    assert sizer.quantity(_signal(Action.CLOSE), _ctx(position="73")) == Decimal(73)


def test_volatility_target_caps_when_vol_unknown() -> None:
    # No closes -> can't estimate vol -> falls back to the max_fraction cap.
    sizer = VolatilityTarget(Decimal("0.02"), max_fraction=Decimal("0.25"))
    qty = sizer.quantity(_signal(Action.BUY), _ctx(price="100", equity="100000"))
    assert qty == Decimal(250)  # 25% of 100k / 100


def test_volatility_target_smaller_for_higher_vol() -> None:
    calm = [100.0 + 0.1 * i for i in range(30)]  # low realized vol
    choppy = [100.0 * (1.1 if i % 2 else 0.9) for i in range(30)]  # high realized vol
    sizer = VolatilityTarget(Decimal("0.01"), lookback=20, max_fraction=Decimal("1"))
    calm_qty = sizer.quantity(_signal(Action.BUY), _ctx(price="100", closes=calm))
    choppy_qty = sizer.quantity(_signal(Action.BUY), _ctx(price="100", closes=choppy))
    assert calm_qty > choppy_qty


def test_invalid_params_rejected() -> None:
    with pytest.raises(ValueError):
        FixedQuantity(Decimal(0))
    with pytest.raises(ValueError):
        FixedFractional(Decimal("1.5"))
    with pytest.raises(ValueError):
        VolatilityTarget(Decimal(0))

"""RiskModel approves orders within limits and rejects concentration/leverage breaches."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from mutualfund.execution.orders import Order, Position, Side
from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.risk.model import PortfolioState, RiskLimits, RiskModel

AAPL = Instrument("AAPL", AssetClass.EQUITY)
OPT = Instrument(
    "AAPL", AssetClass.OPTION, multiplier=Decimal(100),
    expiry=date(2026, 12, 18), strike=Decimal(200), option_type="C",
)


def _portfolio(equity: str, positions=None, marks=None) -> PortfolioState:
    return PortfolioState(Decimal(equity), positions or [], marks or {})


def test_approves_order_within_position_limit() -> None:
    model = RiskModel(RiskLimits(max_position_pct=Decimal("0.25")))
    order = Order(AAPL, Side.BUY, Decimal(100))  # 100 * $100 = $10k = 10% of 100k
    decision = model.check(order, _portfolio("100000", marks={AAPL.key: Decimal(100)}))
    assert decision.approved


def test_rejects_order_over_position_limit() -> None:
    model = RiskModel(RiskLimits(max_position_pct=Decimal("0.25")))
    order = Order(AAPL, Side.BUY, Decimal(300))  # $30k = 30% > 25%
    decision = model.check(order, _portfolio("100000", marks={AAPL.key: Decimal(100)}))
    assert not decision.approved
    assert decision.reason is not None


def test_existing_position_counts_toward_limit() -> None:
    model = RiskModel(RiskLimits(max_position_pct=Decimal("0.25")))
    order = Order(AAPL, Side.BUY, Decimal(100))  # adds to an existing 200
    portfolio = _portfolio(
        "100000",
        positions=[Position(AAPL, Decimal(200), Decimal(100))],
        marks={AAPL.key: Decimal(100)},
    )
    # Projected 300 shares = $30k = 30% > 25%.
    assert not model.check(order, portfolio).approved


def test_sell_reducing_exposure_is_approved() -> None:
    model = RiskModel(RiskLimits(max_position_pct=Decimal("0.10")))
    order = Order(AAPL, Side.SELL, Decimal(200))  # flattens a 200 long
    portfolio = _portfolio(
        "100000",
        positions=[Position(AAPL, Decimal(200), Decimal(100))],
        marks={AAPL.key: Decimal(100)},
    )
    assert model.check(order, portfolio).approved


def test_rejects_options_over_leverage() -> None:
    model = RiskModel(
        RiskLimits(max_position_pct=Decimal("10"), max_options_leverage=Decimal("1.0"))
    )
    # 20 contracts * 100 mult * $60 = $120k notional = 1.2x of 100k equity.
    order = Order(OPT, Side.BUY, Decimal(20))
    decision = model.check(order, _portfolio("100000", marks={OPT.key: Decimal(60)}))
    assert not decision.approved
    assert "leverage" in (decision.reason or "")


def test_rejects_on_non_positive_equity() -> None:
    model = RiskModel()
    order = Order(AAPL, Side.BUY, Decimal(1))
    assert not model.check(order, _portfolio("0", marks={AAPL.key: Decimal(100)})).approved

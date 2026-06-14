"""Performance metrics derived from a hand-built event sequence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from mutualfund.ledger.event import LedgerEvent, LedgerEventType
from mutualfund.ledger.performance import PerformanceCalculator

TS = datetime(2026, 1, 1, tzinfo=UTC)


def _fill(side: str, qty: str, price: str, fee: str = "0", mult: str = "1") -> LedgerEvent:
    return LedgerEvent(
        "s",
        LedgerEventType.FILL,
        {
            "instrument": "AAPL:equity",
            "side": side,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "multiplier": mult,
        },
        TS,
    )


def _mark(equity: str) -> LedgerEvent:
    return LedgerEvent("s", LedgerEventType.MARK, {"equity": equity}, TS)


def test_winning_round_trip() -> None:
    calc = PerformanceCalculator()
    events = [
        _fill("buy", "10", "100"),
        _fill("sell", "10", "110"),  # +100 realized
        _mark("100100"),
    ]
    rec = calc.from_events(events, Decimal(100_000))
    assert rec.num_trades == 1
    assert rec.win_rate == Decimal("1.0000")
    assert rec.net_pnl == Decimal(100)  # from mark: 100100 - 100000
    assert rec.return_pct == Decimal("0.10")


def test_losing_trade_and_win_rate() -> None:
    calc = PerformanceCalculator()
    events = [
        _fill("buy", "10", "100"),
        _fill("sell", "10", "90"),  # losing close
        _fill("buy", "5", "50"),
        _fill("sell", "5", "60"),  # winning close
    ]
    rec = calc.from_events(events, Decimal(100_000))
    assert rec.num_trades == 2
    assert rec.win_rate == Decimal("0.5000")


def test_max_drawdown_from_marks() -> None:
    calc = PerformanceCalculator()
    events = [_mark("100"), _mark("120"), _mark("90"), _mark("110")]
    rec = calc.from_events(events, Decimal(100))
    # peak 120 -> trough 90 => 25% drawdown
    assert rec.max_drawdown_pct == Decimal("25.00")

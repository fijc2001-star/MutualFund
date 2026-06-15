"""Qualification criteria pass/fail correctly and policies aggregate + version."""

from __future__ import annotations

from decimal import Decimal

from mutualfund.ledger.performance import PerformanceRecord
from mutualfund.lifecycle.qualification import (
    MaxConcentration,
    MaxDrawdownCeiling,
    MinPeriod,
    MinTrades,
    NetPositive,
    QualificationInput,
    SharpeFloor,
    baseline_policy,
    demo_policy,
)


def _record(
    *, net_pnl: str = "1000", num_trades: int = 30, max_dd: str = "10",
    sharpe: str | None = "1.0", return_pct: str = "10",
) -> PerformanceRecord:
    return PerformanceRecord(
        starting_cash=Decimal("100000"),
        net_pnl=Decimal(net_pnl),
        return_pct=Decimal(return_pct),
        max_drawdown_pct=Decimal(max_dd),
        num_trades=num_trades,
        win_rate=Decimal("0.6"),
        sharpe=Decimal(sharpe) if sharpe is not None else None,
    )


def _input(
    record: PerformanceRecord, *, days: int = 60, conc: str | None = None
) -> QualificationInput:
    return QualificationInput(record, days, Decimal(conc) if conc is not None else None)


def test_individual_criteria() -> None:
    rec = _record()
    assert NetPositive().assess(_input(rec)).passed
    assert not NetPositive().assess(_input(_record(net_pnl="-1"))).passed

    assert MinTrades(20).assess(_input(rec)).passed
    assert not MinTrades(50).assess(_input(rec)).passed

    assert MinPeriod(30).assess(_input(rec, days=60)).passed
    assert not MinPeriod(90).assess(_input(rec, days=60)).passed

    assert SharpeFloor(Decimal("0.5")).assess(_input(rec)).passed
    assert not SharpeFloor(Decimal("2.0")).assess(_input(rec)).passed
    assert not SharpeFloor(Decimal("0.5")).assess(_input(_record(sharpe=None))).passed

    assert MaxDrawdownCeiling(Decimal("25")).assess(_input(rec)).passed
    assert not MaxDrawdownCeiling(Decimal("25")).assess(_input(_record(max_dd="40"))).passed


def test_max_concentration_requires_measurement() -> None:
    rec = _record()
    assert not MaxConcentration(Decimal("20")).assess(_input(rec, conc=None)).passed
    assert MaxConcentration(Decimal("20")).assess(_input(rec, conc="15")).passed
    assert not MaxConcentration(Decimal("20")).assess(_input(rec, conc="30")).passed


def test_baseline_policy_passes_strong_record() -> None:
    result = baseline_policy().assess(_input(_record()))
    assert result.passed
    assert result.policy_name == "baseline"
    assert result.policy_version == 1
    assert result.failures == []


def test_demo_policy_passes_a_modest_net_positive_record() -> None:
    # Short period + low Sharpe but net positive with enough trades and bounded drawdown.
    rec = _record(net_pnl="600", num_trades=30, max_dd="12", sharpe="0.05")
    result = demo_policy().assess(_input(rec, days=8))
    assert result.passed
    assert result.policy_name == "demo"


def test_baseline_policy_fails_and_reports_each_breach() -> None:
    weak = _record(net_pnl="-500", num_trades=3, max_dd="40", sharpe="0.1")
    result = baseline_policy().assess(_input(weak, days=5))
    assert not result.passed
    failed = {c.name for c in result.failures}
    assert failed == {"min_period", "min_trades", "sharpe_floor", "max_drawdown", "net_positive"}

"""Qualification: the versioned, pluggable bar a bot must clear to be Listed (REQUIREMENTS §5.8).

Each `QualificationCriterion` is a single pass/fail check over a `QualificationInput` (the M10
`PerformanceRecord` plus evaluation metadata the record doesn't carry — period, concentration).
A `QualificationPolicy` is a *named, versioned* set of criteria; the version is recorded on the
bot when it passes, so the exact bar it cleared is auditable even as the policy evolves.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ..ledger.performance import PerformanceRecord


@dataclass(frozen=True, slots=True)
class QualificationInput:
    """Everything a criterion may read: the performance record + evaluation context."""

    record: PerformanceRecord
    evaluation_days: int = 0
    max_name_concentration_pct: Decimal | None = None  # None = not measured


@dataclass(frozen=True, slots=True)
class CriterionResult:
    name: str
    passed: bool
    detail: str


@runtime_checkable
class QualificationCriterion(Protocol):
    @property
    def name(self) -> str: ...

    def assess(self, perf: QualificationInput) -> CriterionResult: ...


@dataclass(frozen=True, slots=True)
class NetPositive:
    name: str = "net_positive"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        pnl = perf.record.net_pnl
        return CriterionResult(self.name, pnl > 0, f"net P&L {pnl}")


@dataclass(frozen=True, slots=True)
class MinTrades:
    min_trades: int
    name: str = "min_trades"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        n = perf.record.num_trades
        detail = f"{n} trades (min {self.min_trades})"
        return CriterionResult(self.name, n >= self.min_trades, detail)


@dataclass(frozen=True, slots=True)
class MinPeriod:
    min_days: int
    name: str = "min_period"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        d = perf.evaluation_days
        detail = f"{d} days (min {self.min_days})"
        return CriterionResult(self.name, d >= self.min_days, detail)


@dataclass(frozen=True, slots=True)
class SharpeFloor:
    floor: Decimal
    name: str = "sharpe_floor"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        sharpe = perf.record.sharpe
        if sharpe is None:
            return CriterionResult(self.name, False, "sharpe not available")
        detail = f"sharpe {sharpe} (min {self.floor})"
        return CriterionResult(self.name, sharpe >= self.floor, detail)


@dataclass(frozen=True, slots=True)
class MaxDrawdownCeiling:
    max_pct: Decimal  # positive percent, e.g. 25 == 25%
    name: str = "max_drawdown"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        dd = perf.record.max_drawdown_pct
        detail = f"drawdown {dd}% (max {self.max_pct}%)"
        return CriterionResult(self.name, dd <= self.max_pct, detail)


@dataclass(frozen=True, slots=True)
class MaxConcentration:
    max_pct: Decimal
    name: str = "max_concentration"

    def assess(self, perf: QualificationInput) -> CriterionResult:
        c = perf.max_name_concentration_pct
        if c is None:
            return CriterionResult(self.name, False, "concentration not measured")
        detail = f"concentration {c}% (max {self.max_pct}%)"
        return CriterionResult(self.name, c <= self.max_pct, detail)


@dataclass(frozen=True, slots=True)
class PolicyResult:
    policy_name: str
    policy_version: int
    passed: bool
    criteria: list[CriterionResult]

    @property
    def failures(self) -> list[CriterionResult]:
        return [c for c in self.criteria if not c.passed]


class QualificationPolicy:
    def __init__(
        self, name: str, version: int, criteria: list[QualificationCriterion]
    ) -> None:
        self.name = name
        self.version = version
        self._criteria = list(criteria)

    def assess(self, perf: QualificationInput) -> PolicyResult:
        results = [c.assess(perf) for c in self._criteria]
        return PolicyResult(self.name, self.version, all(r.passed for r in results), results)


def baseline_policy() -> QualificationPolicy:
    """The global baseline gate (REQUIREMENTS §5.8). Per-risk-tier policies come later."""
    return QualificationPolicy(
        "baseline",
        1,
        [
            MinPeriod(min_days=30),
            MinTrades(min_trades=20),
            SharpeFloor(Decimal("0.5")),
            MaxDrawdownCeiling(Decimal("25")),
            NetPositive(),
        ],
    )

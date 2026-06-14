"""GuardrailPolicy: hard, account-level limits the agent/bot cannot override (REQUIREMENTS §5.6).

Unlike `RiskModel` (a per-order sizing/concentration gate), guardrails halt *all* trading
on an account when a protective threshold is breached: a global kill-switch, an intraday
loss limit, or a max drawdown from the equity peak.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GuardrailLimits:
    daily_loss_limit_pct: Decimal = Decimal("0.05")  # vs. day-start equity
    max_drawdown_pct: Decimal = Decimal("0.20")  # vs. peak equity


@dataclass(frozen=True, slots=True)
class AccountRisk:
    equity: Decimal
    day_start_equity: Decimal
    peak_equity: Decimal
    kill_switch: bool = False


@dataclass(frozen=True, slots=True)
class GuardrailState:
    halted: bool
    reason: str | None = None


class GuardrailPolicy:
    def __init__(self, limits: GuardrailLimits | None = None) -> None:
        self._limits = limits or GuardrailLimits()

    def enforce(self, account: AccountRisk) -> GuardrailState:
        if account.kill_switch:
            return GuardrailState(True, "kill switch engaged")

        if account.day_start_equity > 0:
            daily = (account.equity - account.day_start_equity) / account.day_start_equity
            if daily <= -self._limits.daily_loss_limit_pct:
                return GuardrailState(True, f"daily loss {daily:.1%} breached limit")

        if account.peak_equity > 0:
            drawdown = (account.equity - account.peak_equity) / account.peak_equity
            if drawdown <= -self._limits.max_drawdown_pct:
                return GuardrailState(True, f"drawdown {drawdown:.1%} breached limit")

        return GuardrailState(False)

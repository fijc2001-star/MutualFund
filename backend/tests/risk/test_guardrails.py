"""GuardrailPolicy halts on kill-switch, daily-loss, and drawdown breaches."""

from __future__ import annotations

from decimal import Decimal

from mutualfund.risk.guardrails import AccountRisk, GuardrailLimits, GuardrailPolicy


def _account(equity: str, day_start: str = "100000", peak: str = "100000",
             kill: bool = False) -> AccountRisk:
    return AccountRisk(Decimal(equity), Decimal(day_start), Decimal(peak), kill)


def test_healthy_account_not_halted() -> None:
    policy = GuardrailPolicy()
    assert not policy.enforce(_account("99000")).halted


def test_kill_switch_halts() -> None:
    state = GuardrailPolicy().enforce(_account("100000", kill=True))
    assert state.halted
    assert "kill" in (state.reason or "")


def test_daily_loss_limit_halts() -> None:
    policy = GuardrailPolicy(GuardrailLimits(daily_loss_limit_pct=Decimal("0.05")))
    # Down 6% on the day -> breached.
    assert policy.enforce(_account("94000")).halted
    # Down only 4% -> still trading.
    assert not policy.enforce(_account("96000")).halted


def test_max_drawdown_halts() -> None:
    policy = GuardrailPolicy(GuardrailLimits(max_drawdown_pct=Decimal("0.20")))
    # Peaked at 120k, now 90k -> 25% drawdown -> breached.
    assert policy.enforce(_account("90000", day_start="90000", peak="120000")).halted
    # 110k vs 120k peak -> ~8% -> fine.
    assert not policy.enforce(_account("110000", day_start="110000", peak="120000")).halted

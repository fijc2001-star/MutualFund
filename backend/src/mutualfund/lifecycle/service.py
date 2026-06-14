"""QualificationService: run a policy against a bot's performance and move its lifecycle.

Pass while in Evaluation → promote to Listed and stamp the policy bar it cleared. Breach →
Delist a still-evaluating bot, or Suspend a Listed one (recoverable). Anything else is a
no-op: the service reports the result without forcing an illegal transition.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..foundation.clock import Clock
from ..strategy.models import BotVersion
from .lifecycle import BotLifecycle, BotState
from .qualification import PolicyResult, QualificationInput, QualificationPolicy, baseline_policy


class QualificationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        policy: QualificationPolicy | None = None,
        lifecycle: BotLifecycle | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._policy = policy or baseline_policy()
        self._lifecycle = lifecycle or BotLifecycle(session, clock=clock)

    async def evaluate(
        self, version: BotVersion, perf: QualificationInput, *, actor: str = "system"
    ) -> PolicyResult:
        result = self._policy.assess(perf)
        current = BotState(version.state)
        bar = f"{result.policy_name} v{result.policy_version}"

        if result.passed:
            if current is BotState.EVALUATION:
                version.qualified_policy = result.policy_name
                version.qualified_policy_version = result.policy_version
                await self._lifecycle.transition(
                    version, BotState.LISTED, reason=f"passed {bar}", actor=actor
                )
        else:
            reason = f"failed {bar}: " + "; ".join(c.detail for c in result.failures)
            if current is BotState.EVALUATION:
                await self._lifecycle.transition(
                    version, BotState.DELISTED, reason=reason, actor=actor
                )
            elif current is BotState.LISTED:
                await self._lifecycle.transition(
                    version, BotState.SUSPENDED, reason=reason, actor=actor
                )

        return result

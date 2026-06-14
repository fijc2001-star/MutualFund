"""The bot lifecycle state machine.

State lives on each `BotVersion` (M3). `transition` enforces an allowed-transition map and
writes an audit record on every change, so a bot's lifecycle is itself tamper-evident.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from ..foundation.audit import AuditLog
from ..foundation.clock import Clock, SystemClock
from ..foundation.repository import TenantRepository
from ..strategy.models import BotVersion


class BotState(str, Enum):
    DRAFT = "draft"
    EVALUATION = "evaluation"
    LISTED = "listed"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    LIQUIDATION = "liquidation"
    RETIRED = "retired"


# Allowed forward transitions. A breaching Listed bot is Suspended (recoverable) or Delisted;
# a Delisted bot winds down through Liquidation to Retired.
_ALLOWED: dict[BotState, frozenset[BotState]] = {
    BotState.DRAFT: frozenset({BotState.EVALUATION}),
    BotState.EVALUATION: frozenset({BotState.LISTED, BotState.DELISTED, BotState.DRAFT}),
    BotState.LISTED: frozenset({BotState.SUSPENDED, BotState.DELISTED}),
    BotState.SUSPENDED: frozenset({BotState.LISTED, BotState.DELISTED}),
    BotState.DELISTED: frozenset({BotState.LIQUIDATION}),
    BotState.LIQUIDATION: frozenset({BotState.RETIRED}),
    BotState.RETIRED: frozenset(),
}


class IllegalTransitionError(ValueError):
    """Raised when a state transition is not permitted by the state machine."""


class BotLifecycle:
    def __init__(self, session: AsyncSession, *, clock: Clock | None = None) -> None:
        self._versions: TenantRepository[BotVersion] = TenantRepository(session, BotVersion)
        self._audit = AuditLog(session, clock)
        self._clock = clock or SystemClock()

    @staticmethod
    def can_transition(frm: BotState, to: BotState) -> bool:
        return to in _ALLOWED.get(frm, frozenset())

    async def transition(
        self,
        version: BotVersion,
        to: BotState,
        *,
        reason: str,
        actor: str = "system",
    ) -> BotVersion:
        frm = BotState(version.state)
        if not self.can_transition(frm, to):
            raise IllegalTransitionError(f"{frm.value} -> {to.value} is not allowed")
        version.state = to.value
        await self._versions.add(version)
        await self._audit.record(
            "bot_state_changed",
            actor=actor,
            payload={
                "bot_id": version.bot_id,
                "bot_version_id": version.id,
                "version": version.version,
                "from": frm.value,
                "to": to.value,
                "reason": reason,
            },
        )
        return version

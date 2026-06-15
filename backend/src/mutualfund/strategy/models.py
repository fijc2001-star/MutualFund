"""Persistence for bots and their immutable, versioned definitions (REQUIREMENTS §5.8.1).

A `Bot` is the durable handle a designer owns; each `BotVersion` is a frozen snapshot of a
strategy + params + universe. Publishing never edits params in place — it forks a *new*
version, so the history a buyer relied on can never be rewritten.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..foundation.clock import Clock, SystemClock
from ..foundation.db import Base, Entity, TenantScoped
from ..foundation.repository import TenantRepository
from ..foundation.tenant import TenantContext
from .registry import StrategyRegistry, default_registry
from .strategy import BotDefinition


class Bot(Base, Entity, TenantScoped):
    __tablename__ = "bots"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BotVersion(Base, Entity, TenantScoped):
    __tablename__ = "bot_versions"
    __table_args__ = (
        UniqueConstraint("bot_id", "version", name="uq_botversion_bot_version"),
    )

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(40), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    universe: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_profile_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # The qualification bar this version last cleared (M4) — null until it passes.
    qualified_policy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qualified_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def definition(self) -> BotDefinition:
        """The ORM-free spec `SignalEngine` runs."""
        return BotDefinition(self.strategy_id, dict(self.params), tuple(self.universe))


class BotRegistry:
    """Create bots and fork immutable versions; validates params before a version exists."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        strategies: StrategyRegistry | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session = session
        self._bots: TenantRepository[Bot] = TenantRepository(session, Bot)
        self._versions: TenantRepository[BotVersion] = TenantRepository(session, BotVersion)
        self._strategies = strategies or default_registry
        self._clock = clock or SystemClock()

    async def create_bot(self, *, name: str, owner_id: str) -> Bot:
        bot = Bot(
            name=name,
            owner_id=owner_id,
            current_version=0,
            state="draft",
            created_at=self._clock.now(),
        )
        return await self._bots.add(bot)

    async def publish(
        self,
        bot: Bot,
        *,
        strategy_id: str,
        params: Mapping[str, Any],
        universe: Sequence[str] = (),
        risk_profile_id: str | None = None,
    ) -> BotVersion:
        """Fork a new immutable version. Raises if params fail the strategy's schema."""
        validated: BaseModel = self._strategies.validate(strategy_id, params)
        version = BotVersion(
            bot_id=bot.id,
            version=bot.current_version + 1,
            strategy_id=strategy_id,
            params=validated.model_dump(mode="json"),
            universe=list(universe),
            risk_profile_id=risk_profile_id,
            state="draft",
            created_at=self._clock.now(),
        )
        await self._versions.add(version)
        bot.current_version = version.version
        await self._bots.add(bot)
        return version

    async def versions(self, bot_id: str) -> list[BotVersion]:
        """All versions of a bot for the current tenant, oldest → newest."""
        stmt = (
            select(BotVersion)
            .where(
                BotVersion.bot_id == bot_id,
                BotVersion.tenant_id == TenantContext.get(),
            )
            .order_by(BotVersion.version)
        )
        result = await self._versions.session.execute(stmt)
        return list(result.scalars().all())

    async def get_bot(self, bot_id: str) -> Bot | None:
        """A bot by id, scoped to the current tenant."""
        return await self._bots.get(bot_id)

    async def list_bots(self, owner_id: str) -> list[Bot]:
        """A designer's bots for the current tenant, oldest → newest."""
        stmt = (
            select(Bot)
            .where(Bot.tenant_id == TenantContext.get(), Bot.owner_id == owner_id)
            .order_by(Bot.created_at)
        )
        result = await self._bots.session.execute(stmt)
        return list(result.scalars().all())

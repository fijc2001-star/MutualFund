"""Persistence for the marketplace: public listings of qualified bots.

A `Listing` is a designer's public offer of one *qualified* (Listed) bot version — title,
description, price, and a frozen track-record snapshot taken at publish time. The version it
points to is immutable (publishing forks a new `BotVersion`), so the record a buyer relied on
can never be rewritten under them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..foundation.db import Base, Entity, TenantScoped


class Listing(Base, Entity, TenantScoped):
    __tablename__ = "listings"

    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"), index=True, nullable=False)
    bot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    # Denormalized for cheap browse cards.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(40), nullable=False)

    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = free
    billing_period: Mapped[str] = mapped_column(
        String(12), default="monthly", nullable=False
    )  # "monthly" | "once" | "free"
    status: Mapped[str] = mapped_column(
        String(12), default="active", nullable=False
    )  # "active" | "paused" | "withdrawn"

    # Track record snapshot (M10 perf) captured at publish time, so browse/detail are cheap.
    track_record: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

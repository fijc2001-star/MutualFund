"""Persistence for subscriptions — a lightweight reference, not a copy of the bot stream."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..foundation.db import Base, Entity, TenantScoped


class Subscription(Base, Entity, TenantScoped):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "subscriber", "listing_id",
            name="uq_subscription_tenant_subscriber_listing",
        ),
    )

    subscriber: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # The marketplace listing this subscription is for (M-D/M-E).
    listing_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(40), nullable=False)
    # Stable id of the *bot's* shared signal stream on the ledger (not per-subscription).
    stream_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # The window start: replay shows the bot's signals from here onward.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

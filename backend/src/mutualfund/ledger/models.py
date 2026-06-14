"""Append-only, hash-chained ledger table (REQUIREMENTS §5.8.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..foundation.db import Base, Entity, TenantScoped


class LedgerEntry(Base, Entity, TenantScoped):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("stream_id", "seq", name="uq_ledger_stream_seq"),
    )

    stream_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

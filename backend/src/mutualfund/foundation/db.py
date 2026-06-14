"""Async SQLAlchemy engine/session, declarative base, and shared column mixins.

Multi-tenancy strategy (v1): shared DB, ``tenant_id`` column on every tenant-scoped
table, filtered automatically by the repository layer (REQUIREMENTS §7, IMPLEMENTATION_PLAN §0).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from ..config import get_settings
from .ids import new_id


class Base(DeclarativeBase):
    pass


class Entity:
    """Primary-key mixin for all persisted aggregates."""

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


class TenantScoped:
    """Marks a table as belonging to a tenant; enforced by TenantRepository."""

    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine(database_url: str) -> AsyncEngine:
    # In-memory sqlite needs a shared static pool so all sessions see the same DB.
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        return create_async_engine(
            database_url,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(database_url, future=True, pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().database_url)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


def configure_engine(engine: AsyncEngine) -> None:
    """Override the engine/sessionmaker (used by tests)."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_all() -> None:
    """Create tables from metadata. Dev/test convenience; prod uses Alembic."""
    # Import models so they register on Base.metadata before create_all.
    from .. import iam  # noqa: F401
    from . import audit  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

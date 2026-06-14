"""Unit of Work: a transaction-scoped session wrapper (ARCHITECTURE §3.1)."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_sessionmaker


class UnitOfWork:
    def __init__(self) -> None:
        self._sessionmaker = get_sessionmaker()
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork used outside of its async context")
        return self._session

    async def __aenter__(self) -> UnitOfWork:
        self._session = self._sessionmaker()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
            self._session = None

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

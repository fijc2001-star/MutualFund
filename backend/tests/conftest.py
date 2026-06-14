"""Test configuration: in-memory SQLite, schema creation, tenant fixtures.

Env is set before importing app modules so the cached Settings pick it up.
SQLite (aiosqlite, StaticPool) lets the full suite run without Docker/Postgres.
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEFAULT_TENANT_ID", "00000000000000000000000000000000")
os.environ.setdefault("ROOT_ADMIN_EMAIL", "root@example.com")
os.environ.setdefault("MARKETDATA_PROVIDER", "fake")

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from mutualfund.foundation.db import create_all  # noqa: E402
from mutualfund.foundation.ids import TenantId  # noqa: E402
from mutualfund.foundation.tenant import TenantContext  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _ensure_schema() -> AsyncIterator[None]:
    await create_all()  # checkfirst=True → safe to call per test
    yield


@pytest.fixture
def tenant_id() -> TenantId:
    return TenantId(uuid.uuid4().hex)


@pytest_asyncio.fixture
async def tenant_ctx(tenant_id: TenantId) -> AsyncIterator[TenantId]:
    token = TenantContext.set(tenant_id)
    try:
        yield tenant_id
    finally:
        TenantContext.reset(token)

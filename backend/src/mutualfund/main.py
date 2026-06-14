"""FastAPI application factory and lifespan wiring (IMPLEMENTATION_PLAN §0, §2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .foundation.db import create_all
from .foundation.ids import TenantId
from .foundation.tenant import TenantContext
from .foundation.uow import UnitOfWork
from .iam.bootstrap import ensure_root_admin
from .iam.oauth import init_providers
from .iam.router import router as auth_router
from .marketdata.router import router as marketdata_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_providers()
    # Dev convenience: ensure schema exists (prod uses Alembic migrations).
    if not settings.is_production:
        await create_all()
    # Bootstrap the configured root admin.
    token = TenantContext.set(TenantId(settings.default_tenant_id))
    try:
        async with UnitOfWork() as uow:
            await ensure_root_admin(uow.session)
    finally:
        TenantContext.reset(token)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(marketdata_router)
    return app


app = create_app()

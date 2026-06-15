"""Auth endpoints: OAuth login/callback, token refresh, logout, and /me."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import get_settings
from ..foundation.ids import TenantId
from ..foundation.uow import UnitOfWork
from .deps import CurrentPrincipal
from .oauth import get_provider
from .roles import Role
from .service import IdentityService

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class DevLoginRequest(BaseModel):
    email: str
    role: str = "user"


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    role: str


def _redirect_uri(provider: str) -> str:
    base = get_settings().oauth_redirect_base_url.rstrip("/")
    return f"{base}/auth/{provider}/callback"


@router.get("/{provider}/login")
async def login(provider: str) -> RedirectResponse:
    try:
        oauth = get_provider(provider)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    state = secrets.token_urlsafe(24)
    url = oauth.authorization_url(_redirect_uri(provider), state=state)
    return RedirectResponse(url)


@router.get("/{provider}/callback", response_model=TokenResponse)
async def callback(provider: str, code: str = Query(...)) -> TokenResponse:
    try:
        oauth = get_provider(provider)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    info = await oauth.exchange_code(code, _redirect_uri(provider))
    tenant_id = TenantId(get_settings().default_tenant_id)
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        _, tokens = await service.login_with_oauth(info)
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(body: DevLoginRequest) -> TokenResponse:
    """Issue tokens for a test user without OAuth. Disabled in production."""
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dev login is disabled in production"
        )
    try:
        role = Role(body.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {body.role}"
        ) from exc
    tenant_id = TenantId(settings.default_tenant_id)
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        _, tokens = await service.dev_login(body.email, role)
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    tenant_id = TenantId(get_settings().default_tenant_id)
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        try:
            tokens = await service.refresh(body.refresh_token)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
            ) from exc
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest) -> None:
    tenant_id = TenantId(get_settings().default_tenant_id)
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        await service.logout(body.refresh_token)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        email=principal.email,
        role=principal.role.value,
    )

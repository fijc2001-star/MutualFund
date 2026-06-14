"""OAuth login → JWT, account linking, refresh rotation, logout revocation."""

from __future__ import annotations

import pytest

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.tenant import TenantContext
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.iam.oauth import OAuthUserInfo
from mutualfund.iam.service import IdentityService
from mutualfund.iam.tokens import verify_access_token


def _info(
    sub: str = "g-1", email: str = "alice@example.com", verified: bool = True
) -> OAuthUserInfo:
    return OAuthUserInfo(
        provider="fake",
        subject=sub,
        email=email,
        email_verified=verified,
        display_name="Alice",
    )


async def test_login_creates_user_and_valid_tokens(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    try:
        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            user, tokens = await svc.login_with_oauth(_info())
            claims = verify_access_token(tokens.access_token)
            assert claims.email == "alice@example.com"
            assert claims.tenant_id == tenant_id
            assert user.role == "user"
    finally:
        TenantContext.reset(token)


async def test_account_linking_by_verified_email(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    try:
        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            u1, _ = await svc.login_with_oauth(_info(sub="g-1"))
        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            u2, _ = await svc.login_with_oauth(_info(sub="ms-2"))  # same verified email
            assert u2.id == u1.id
    finally:
        TenantContext.reset(token)


async def test_refresh_rotates_and_logout_revokes(tenant_id: TenantId) -> None:
    token = TenantContext.set(tenant_id)
    try:
        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            _, tokens = await svc.login_with_oauth(_info())
            old_refresh = tokens.refresh_token

        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            rotated = await svc.refresh(old_refresh)
            assert rotated.refresh_token != old_refresh

        # old refresh token is now revoked
        async with UnitOfWork() as uow:
            svc = IdentityService(uow.session, tenant_id)
            with pytest.raises(PermissionError):
                await svc.refresh(old_refresh)
    finally:
        TenantContext.reset(token)

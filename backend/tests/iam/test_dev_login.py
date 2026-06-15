"""Dev login find-or-creates a user, applies the role, and issues a valid access token."""

from __future__ import annotations

from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.iam.roles import Role
from mutualfund.iam.service import IdentityService
from mutualfund.iam.tokens import verify_access_token


async def test_dev_login_creates_user_and_issues_token(tenant_id: TenantId) -> None:
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        user, tokens = await service.dev_login("designer@example.com", Role.DESIGNER)

        assert user.email == "designer@example.com"
        assert user.role == Role.DESIGNER.value
        assert tokens.access_token and tokens.refresh_token

        claims = verify_access_token(tokens.access_token)
        assert claims.email == "designer@example.com"
        assert claims.role is Role.DESIGNER


async def test_dev_login_is_idempotent_and_updates_role(tenant_id: TenantId) -> None:
    async with UnitOfWork() as uow:
        service = IdentityService(uow.session, tenant_id)
        first, _ = await service.dev_login("u@example.com", Role.USER)
        second, _ = await service.dev_login("u@example.com", Role.ADMIN)

        assert first.id == second.id  # same user
        assert second.role == Role.ADMIN.value

"""Identity service: turn a verified OAuth login into a User + tokens.

Account linking: a verified email maps to one user per tenant (REQUIREMENTS §5.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..foundation.ids import TenantId, UserId, new_id
from .models import Identity, RefreshToken, User
from .oauth import OAuthUserInfo
from .roles import Role
from .tokens import (
    issue_access_token,
    issue_refresh_token,
    verify_refresh_token,
)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityService:
    def __init__(self, session: AsyncSession, tenant_id: TenantId) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def login_with_oauth(self, info: OAuthUserInfo) -> tuple[User, TokenPair]:
        user = await self._find_or_create_user(info)
        tokens = await self._issue_pair(user)
        return user, tokens

    async def dev_login(self, email: str, role: Role = Role.USER) -> tuple[User, TokenPair]:
        """Dev-only shortcut: find-or-create a user by email and issue tokens (no OAuth).

        Lets the app be exercised end to end before Google credentials exist. Gated to
        non-production by the caller. The requested role is applied so designer/admin views
        can be tried out.
        """
        info = OAuthUserInfo(
            provider="dev",
            subject=f"dev:{email}",
            email=email,
            email_verified=True,
            display_name=email.split("@")[0],
        )
        user = await self._find_or_create_user(info)
        if user.role != role.value:
            user.role = role.value
            await self.session.flush()
        tokens = await self._issue_pair(user)
        return user, tokens

    async def _find_or_create_user(self, info: OAuthUserInfo) -> User:
        # 1) existing federated identity?
        identity = await self.session.scalar(
            select(Identity).where(
                Identity.provider == info.provider,
                Identity.provider_subject == info.subject,
            )
        )
        if identity is not None:
            user = await self.session.get(User, identity.user_id)
            assert user is not None
            return user

        # 2) account linking by verified email within this tenant
        user = None
        if info.email_verified:
            user = await self.session.scalar(
                select(User).where(
                    User.tenant_id == self.tenant_id, User.email == info.email
                )
            )

        # 3) otherwise create a fresh user (default role = USER)
        if user is None:
            user = User(
                id=new_id(),
                tenant_id=self.tenant_id,
                email=info.email,
                email_verified=info.email_verified,
                display_name=info.display_name,
                role=Role.USER.value,
                status="active",
                created_at=_now(),
            )
            self.session.add(user)
            await self.session.flush()

        self.session.add(
            Identity(
                id=new_id(),
                tenant_id=self.tenant_id,
                provider=info.provider,
                provider_subject=info.subject,
                user_id=user.id,
                created_at=_now(),
            )
        )
        await self.session.flush()
        return user

    async def _issue_pair(self, user: User) -> TokenPair:
        access = issue_access_token(
            UserId(user.id), TenantId(user.tenant_id), user.email, Role(user.role)
        )
        refresh = issue_refresh_token(UserId(user.id), TenantId(user.tenant_id))
        self.session.add(
            RefreshToken(
                id=new_id(),
                tenant_id=user.tenant_id,
                user_id=user.id,
                jti=refresh.jti,
                expires_at=refresh.expires_at,
                revoked=False,
                created_at=_now(),
            )
        )
        await self.session.flush()
        return TokenPair(
            access_token=access.token,
            refresh_token=refresh.token,
            access_expires_at=access.expires_at,
            refresh_expires_at=refresh.expires_at,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        user_id, tenant_id, jti = verify_refresh_token(refresh_token)
        record = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        if record is None or record.revoked:
            raise PermissionError("Refresh token is invalid or revoked")
        # SQLite returns naive datetimes; coerce to aware UTC for comparison.
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= _now():
            raise PermissionError("Refresh token expired")
        # Rotate: revoke the old, issue a new pair.
        record.revoked = True
        user = await self.session.get(User, user_id)
        if user is None:
            raise PermissionError("User no longer exists")
        return await self._issue_pair(user)

    async def logout(self, refresh_token: str) -> None:
        _, _, jti = verify_refresh_token(refresh_token)
        record = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        if record is not None:
            record.revoked = True
            await self.session.flush()

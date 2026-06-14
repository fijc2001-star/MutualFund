"""Root-admin bootstrap from configuration (REQUIREMENTS §1.1).

The root admin is created from env/secret at startup, never via the UI. Idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..foundation.ids import new_id
from .models import User
from .roles import Role


async def ensure_root_admin(session: AsyncSession) -> User | None:
    """Ensure the configured root-admin user exists with ROOT_ADMIN role."""
    settings = get_settings()
    if not settings.root_admin_email:
        return None

    tenant_id = settings.default_tenant_id
    email = settings.root_admin_email.lower()

    user = await session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    if user is None:
        user = User(
            id=new_id(),
            tenant_id=tenant_id,
            email=email,
            email_verified=True,
            display_name="Root Admin",
            role=Role.ROOT_ADMIN.value,
            status="active",
            created_at=datetime.now(UTC),
        )
        session.add(user)
    elif user.role != Role.ROOT_ADMIN.value:
        user.role = Role.ROOT_ADMIN.value

    await session.flush()
    return user

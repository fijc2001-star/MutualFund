from __future__ import annotations

import pytest

from mutualfund.foundation.ids import TenantId, UserId
from mutualfund.iam.roles import (
    AuthorizationError,
    Principal,
    Role,
    RoleService,
    cumulative_roles,
    has_at_least,
)


def _principal(role: Role) -> Principal:
    return Principal(
        user_id=UserId("u"), tenant_id=TenantId("t"), email="e@x.com", role=role
    )


def test_roles_are_cumulative() -> None:
    assert cumulative_roles(Role.DESIGNER) == {Role.USER, Role.DESIGNER}
    assert cumulative_roles(Role.ROOT_ADMIN) == set(Role)


def test_has_at_least() -> None:
    assert has_at_least(Role.ADMIN, Role.DESIGNER)
    assert not has_at_least(Role.USER, Role.ADMIN)


def test_require_allows_and_denies() -> None:
    RoleService.require(_principal(Role.ADMIN), Role.DESIGNER)  # no raise
    with pytest.raises(AuthorizationError):
        RoleService.require(_principal(Role.USER), Role.ADMIN)

"""Roles, cumulative privileges, and RBAC checks (REQUIREMENTS §1.1, §5.1).

Roles are cumulative: Designer ⊃ User; Admin ⊃ Designer; RootAdmin ⊃ Admin.
A user stores their highest role; ``cumulative_roles`` expands it to the full set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..foundation.ids import TenantId, UserId


class Role(str, Enum):
    USER = "user"
    DESIGNER = "designer"
    ADMIN = "admin"
    ROOT_ADMIN = "root_admin"


# Lowest → highest. Index encodes privilege level.
_ORDER: list[Role] = [Role.USER, Role.DESIGNER, Role.ADMIN, Role.ROOT_ADMIN]


def rank(role: Role) -> int:
    return _ORDER.index(role)


def cumulative_roles(role: Role) -> set[Role]:
    """All roles at or below the given role."""
    return set(_ORDER[: rank(role) + 1])


def has_at_least(held: Role, required: Role) -> bool:
    return rank(held) >= rank(required)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, derived from a verified access token."""

    user_id: UserId
    tenant_id: TenantId
    email: str
    role: Role

    @property
    def roles(self) -> set[Role]:
        return cumulative_roles(self.role)

    def has(self, required: Role) -> bool:
        return has_at_least(self.role, required)


class AuthorizationError(PermissionError):
    pass


class RoleService:
    """Authorization helper. (Authentication answers *who*; this answers *what*.)"""

    @staticmethod
    def roles_of(role: Role) -> set[Role]:
        return cumulative_roles(role)

    @staticmethod
    def require(principal: Principal, required: Role) -> None:
        if not principal.has(required):
            raise AuthorizationError(
                f"Requires role >= {required.value}; principal has {principal.role.value}"
            )

"""Request-scoped tenant context (contextvar). Set from the authenticated principal.

Tenancy is enforced at the repository layer, not per-feature (ARCHITECTURE §5).
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from .ids import TenantId

_current_tenant: ContextVar[TenantId | None] = ContextVar("current_tenant", default=None)


class NoTenantInContextError(RuntimeError):
    pass


class TenantContext:
    @staticmethod
    def set(tenant_id: TenantId) -> Token[TenantId | None]:
        return _current_tenant.set(tenant_id)

    @staticmethod
    def get() -> TenantId:
        tid = _current_tenant.get()
        if tid is None:
            raise NoTenantInContextError("No tenant set in the current context")
        return tid

    @staticmethod
    def get_optional() -> TenantId | None:
        return _current_tenant.get()

    @staticmethod
    def reset(token: Token[TenantId | None]) -> None:
        _current_tenant.reset(token)

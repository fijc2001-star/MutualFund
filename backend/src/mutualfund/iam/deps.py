"""FastAPI dependencies: authenticate the caller and enforce RBAC + tenancy.

current_principal decodes the bearer token, sets the TenantContext for the request,
and yields a Principal. require_role builds a guard dependency for a minimum role.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from ..foundation.tenant import TenantContext
from .roles import AuthorizationError, Principal, Role, RoleService
from .tokens import TokenError, verify_access_token


async def current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> AsyncIterator[Principal]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_access_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    principal = Principal(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        email=claims.email,
        role=claims.role,
    )
    token_ctx = TenantContext.set(principal.tenant_id)
    try:
        yield principal
    finally:
        TenantContext.reset(token_ctx)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_role(
    required: Role,
) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    async def _guard(principal: CurrentPrincipal) -> Principal:
        try:
            RoleService.require(principal, required)
        except AuthorizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            ) from exc
        return principal

    return _guard

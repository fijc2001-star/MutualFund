"""JWT issuance/verification for our own session tokens (REQUIREMENTS §5.1).

Access tokens are short-lived and stateless. Refresh tokens carry a jti recorded
server-side (models.RefreshToken) so they can be rotated and revoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from ..config import get_settings
from ..foundation.ids import TenantId, UserId, new_id
from .roles import Role

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UserId
    tenant_id: TenantId
    email: str
    role: Role


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def issue_access_token(
    user_id: UserId, tenant_id: TenantId, email: str, role: Role
) -> IssuedToken:
    settings = get_settings()
    jti = new_id()
    exp = _now() + timedelta(seconds=settings.access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tid": tenant_id,
        "email": email,
        "role": role.value,
        "type": "access",
        "jti": jti,
        "exp": exp,
        "iat": _now(),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return IssuedToken(token=token, jti=jti, expires_at=exp)


def issue_refresh_token(user_id: UserId, tenant_id: TenantId) -> IssuedToken:
    settings = get_settings()
    jti = new_id()
    exp = _now() + timedelta(seconds=settings.refresh_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tid": tenant_id,
        "type": "refresh",
        "jti": jti,
        "exp": exp,
        "iat": _now(),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return IssuedToken(token=token, jti=jti, expires_at=exp)


def _decode(token: str, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"Expected {expected_type} token, got {payload.get('type')}")
    return payload


def verify_access_token(token: str) -> AccessClaims:
    payload = _decode(token, "access")
    return AccessClaims(
        user_id=UserId(payload["sub"]),
        tenant_id=TenantId(payload["tid"]),
        email=payload["email"],
        role=Role(payload["role"]),
    )


def verify_refresh_token(token: str) -> tuple[UserId, TenantId, str]:
    """Return (user_id, tenant_id, jti). Revocation is checked against the DB by the caller."""
    payload = _decode(token, "refresh")
    return UserId(payload["sub"]), TenantId(payload["tid"]), payload["jti"]

"""Typed identifiers. UUID4 hex strings under the hood, distinct types at the boundary."""

from __future__ import annotations

import uuid
from typing import NewType

TenantId = NewType("TenantId", str)
UserId = NewType("UserId", str)
IdentityId = NewType("IdentityId", str)
BotId = NewType("BotId", str)
SubscriptionId = NewType("SubscriptionId", str)
AuditEventId = NewType("AuditEventId", str)


def new_id() -> str:
    """Generate a new opaque id (uuid4 hex, 32 chars)."""
    return uuid.uuid4().hex

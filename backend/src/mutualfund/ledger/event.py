"""Ledger event value type + canonical serialization for hashing.

Convention: payloads are **JSON-native** — monetary values are decimal *strings*, not
Decimal/float — so JSON storage and the hash chain are reproducible and exact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

GENESIS_HASH = "0" * 64


class LedgerEventType(str, Enum):
    SIGNAL = "signal"
    FILL = "fill"
    PARAM_SET = "param_set"
    MARK = "mark"


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    stream_id: str
    event_type: LedgerEventType
    payload: dict[str, Any]
    ts: datetime


def canonical(event: LedgerEvent) -> str:
    """Deterministic JSON encoding used as the hashed representation of an event.

    `ts` is normalized to UTC so the hash is stable across DB round-trips (SQLite
    drops tzinfo; naive values are assumed UTC).
    """
    ts = event.ts
    ts_utc = ts.astimezone(UTC) if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    return json.dumps(
        {
            "stream_id": event.stream_id,
            "event_type": event.event_type.value,
            "payload": event.payload,
            "ts": ts_utc.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def chain_hash(prev_hash: str, event: LedgerEvent) -> str:
    return hashlib.sha256((prev_hash + canonical(event)).encode("utf-8")).hexdigest()

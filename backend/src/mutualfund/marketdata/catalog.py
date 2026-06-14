"""Instrument catalog. In-memory reference data for Phase 1; DB-backed later.

Instruments are global reference data (not tenant-scoped).
"""

from __future__ import annotations

from ..foundation.instrument import Instrument


class InstrumentCatalog:
    def __init__(self) -> None:
        self._by_key: dict[str, Instrument] = {}

    def add(self, instrument: Instrument) -> Instrument:
        self._by_key[instrument.key] = instrument
        return instrument

    def get(self, key: str) -> Instrument | None:
        return self._by_key.get(key)

    def all(self) -> list[Instrument]:
        return list(self._by_key.values())

    def remove(self, key: str) -> None:
        self._by_key.pop(key, None)

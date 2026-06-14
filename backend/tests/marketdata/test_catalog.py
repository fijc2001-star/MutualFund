from __future__ import annotations

from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.marketdata.catalog import InstrumentCatalog


def test_catalog_crud() -> None:
    catalog = InstrumentCatalog()
    ins = Instrument("AAPL", AssetClass.EQUITY)
    catalog.add(ins)
    assert catalog.get(ins.key) == ins
    assert ins in catalog.all()
    catalog.remove(ins.key)
    assert catalog.get(ins.key) is None

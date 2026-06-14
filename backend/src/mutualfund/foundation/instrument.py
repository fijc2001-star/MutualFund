"""The Instrument value object and asset-class taxonomy (ARCHITECTURE §3.1).

Asset-class-agnostic core: equities + options now, futures/crypto/fx later
(REQUIREMENTS §6). Money/price values use Decimal, never float.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal


class AssetClass(str, Enum):
    EQUITY = "equity"
    OPTION = "option"
    # FUTURE = "future"; CRYPTO = "crypto"; FX = "fx"  # added later behind same model


OptionType = Literal["C", "P"]


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    asset_class: AssetClass
    multiplier: Decimal = Decimal(1)
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: OptionType | None = None
    tick_size: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if self.asset_class is AssetClass.OPTION:
            if self.expiry is None or self.strike is None or self.option_type is None:
                raise ValueError(
                    "Option instruments require expiry, strike, and option_type"
                )
        else:
            if self.expiry is not None or self.strike is not None or self.option_type is not None:
                raise ValueError(
                    f"{self.asset_class} instruments must not carry option fields"
                )

    @property
    def key(self) -> str:
        """Stable string key (used by the instrument catalog)."""
        if self.asset_class is AssetClass.OPTION:
            assert self.expiry is not None and self.strike is not None
            return f"{self.symbol}:{self.asset_class.value}:{self.expiry.isoformat()}:{self.strike}:{self.option_type}"
        return f"{self.symbol}:{self.asset_class.value}"

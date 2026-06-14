"""SandboxLedger — a per-subscription paper account (an ExecutionVenue).

Executes orders via the four fill models, updates cash/positions, and appends a `fill`
event to the hash-chained EventLedger (M10). The ledger is the source of truth:
positions can be rebuilt by replaying it.
"""

from __future__ import annotations

from decimal import Decimal

from ..foundation.clock import Clock, SystemClock
from ..foundation.instrument import AssetClass, Instrument
from ..ledger.event import LedgerEvent, LedgerEventType
from ..ledger.ledger import EventLedger
from .fills import (
    CommissionModel,
    CrossSpreadFill,
    FillPriceModel,
    FixedBpsSlippage,
    OptionsPricingModel,
    QuoteOptionsPricing,
    SlippageModel,
    StandardCommission,
)
from .orders import Fill, MarketSnapshot, Order, Position, Side

ZERO = Decimal(0)


class SandboxLedger:
    def __init__(
        self,
        ledger: EventLedger,
        stream_id: str,
        *,
        starting_cash: Decimal = Decimal(100_000),
        price_model: FillPriceModel | None = None,
        slippage_model: SlippageModel | None = None,
        commission_model: CommissionModel | None = None,
        options_model: OptionsPricingModel | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._ledger = ledger
        self._stream = stream_id
        self._cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._price = price_model or CrossSpreadFill()
        self._slippage = slippage_model or FixedBpsSlippage()
        self._commission = commission_model or StandardCommission()
        self._options = options_model or QuoteOptionsPricing()
        self._clock = clock or SystemClock()

    # --- ExecutionVenue ---

    async def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill:
        base = self._base_price(order, snapshot)
        price = self._slippage.adjust(base, order)
        fee = self._commission.fee(order, price)
        mult = order.instrument.multiplier
        notional = price * order.quantity * mult

        if order.side is Side.BUY:
            self._cash -= notional + fee
            self._apply_buy(order.instrument, order.quantity, price)
        else:
            self._cash += notional - fee
            self._apply_sell(order.instrument, order.quantity)

        fill = Fill(
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            price=price,
            fee=fee,
            ts=self._clock.now(),
        )
        await self._ledger.append(
            LedgerEvent(
                stream_id=self._stream,
                event_type=LedgerEventType.FILL,
                payload={
                    "instrument": order.instrument.key,
                    "symbol": order.instrument.symbol,
                    "asset_class": order.instrument.asset_class.value,
                    "multiplier": str(mult),
                    "side": order.side.value,
                    "quantity": str(order.quantity),
                    "price": str(price),
                    "fee": str(fee),
                },
                ts=fill.ts,
            )
        )
        return fill

    def positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.quantity != 0]

    def cash(self) -> Decimal:
        return self._cash

    def equity(self, snapshot: MarketSnapshot) -> Decimal:
        total = self._cash
        for pos in self._positions.values():
            if pos.quantity == 0:
                continue
            mark = self._mark(pos.instrument, snapshot)
            total += pos.quantity * mark * pos.instrument.multiplier
        return total

    async def mark_to_market(self, snapshot: MarketSnapshot) -> Decimal:
        equity = self.equity(snapshot)
        await self._ledger.append(
            LedgerEvent(
                stream_id=self._stream,
                event_type=LedgerEventType.MARK,
                payload={"equity": str(equity)},
                ts=self._clock.now(),
            )
        )
        return equity

    # --- internals ---

    def _base_price(self, order: Order, snapshot: MarketSnapshot) -> Decimal:
        if order.instrument.asset_class is AssetClass.OPTION:
            return self._options.fill_price(order.instrument, snapshot, order.side)
        return self._price.price(order, snapshot)

    def _mark(self, instrument: Instrument, snapshot: MarketSnapshot) -> Decimal:
        if instrument.asset_class is AssetClass.OPTION:
            return self._options.mark(instrument, snapshot)
        return snapshot.quote(instrument).last

    def _apply_buy(self, instrument: Instrument, qty: Decimal, price: Decimal) -> None:
        pos = self._positions.get(instrument.key)
        if pos is None or pos.quantity == 0:
            self._positions[instrument.key] = Position(instrument, qty, price)
            return
        new_qty = pos.quantity + qty
        pos.avg_price = (pos.quantity * pos.avg_price + qty * price) / new_qty
        pos.quantity = new_qty

    def _apply_sell(self, instrument: Instrument, qty: Decimal) -> None:
        pos = self._positions.get(instrument.key)
        if pos is None:
            self._positions[instrument.key] = Position(instrument, -qty, ZERO)
            return
        pos.quantity -= qty  # avg unchanged on reduction (v1: no short avg tracking)

"""Sandbox execution: fills, cash, options MTM, ledger writes, isolation, end-to-end."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from mutualfund.execution.orders import MarketSnapshot, Order, Side
from mutualfund.execution.sandbox import SandboxLedger
from mutualfund.foundation.clock import FixedClock
from mutualfund.foundation.ids import TenantId
from mutualfund.foundation.instrument import AssetClass, Instrument
from mutualfund.foundation.uow import UnitOfWork
from mutualfund.ledger.event import LedgerEventType
from mutualfund.ledger.ledger import EventLedger
from mutualfund.ledger.performance import PerformanceCalculator
from mutualfund.marketdata.types import Quote

CLOCK = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
AAPL = Instrument("AAPL", AssetClass.EQUITY)


def _snapshot(bid: str, ask: str, last: str) -> MarketSnapshot:
    q = Quote(AAPL, Decimal(bid), Decimal(ask), Decimal(last), CLOCK.now())
    return MarketSnapshot({AAPL.key: q})


async def test_equity_buy_then_sell_cash_and_fill_prices(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        sb = SandboxLedger(
            led, "sub-1", starting_cash=Decimal(10_000), clock=CLOCK
        )
        # No slippage/commission for exact assertions.
        sb._slippage.adjust = lambda price, order: price  # type: ignore[method-assign]
        snap = _snapshot("99", "101", "100")

        buy = await sb.submit(Order(AAPL, Side.BUY, Decimal(10)), snap)
        assert buy.price == Decimal(101)  # cross spread -> ask
        assert sb.cash() == Decimal(10_000) - Decimal(1010)
        assert sb.positions()[0].quantity == Decimal(10)

        sell = await sb.submit(Order(AAPL, Side.SELL, Decimal(10)), snap)
        assert sell.price == Decimal(99)  # cross spread -> bid
        assert sb.positions() == []  # flat


async def test_fills_are_recorded_on_ledger(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        sb = SandboxLedger(led, "sub-2", starting_cash=Decimal(10_000), clock=CLOCK)
        snap = _snapshot("99", "101", "100")
        await sb.submit(Order(AAPL, Side.BUY, Decimal(1)), snap)
        await sb.submit(Order(AAPL, Side.SELL, Decimal(1)), snap)
        events = await led.replay("sub-2")
        fills = [e for e in events if e.event_type is LedgerEventType.FILL]
        assert len(fills) == 2
        assert (await led.verify("sub-2")).ok


async def test_options_mark_to_market(tenant_ctx: TenantId) -> None:
    opt = Instrument(
        "AAPL",
        AssetClass.OPTION,
        expiry=datetime(2026, 6, 1, tzinfo=UTC).date(),
        strike=Decimal(100),
        option_type="C",
        multiplier=Decimal(100),
    )
    q1 = Quote(opt, Decimal("4.9"), Decimal("5.1"), Decimal("5.0"), CLOCK.now())
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        sb = SandboxLedger(led, "sub-3", starting_cash=Decimal(10_000), clock=CLOCK)
        sb._slippage.adjust = lambda price, order: price  # type: ignore[method-assign]
        await sb.submit(Order(opt, Side.BUY, Decimal(1)), MarketSnapshot({opt.key: q1}))
        # 1 contract @ 5.10 ask * 100 multiplier = 510 + 0.65 fee
        assert sb.cash() == Decimal(10_000) - Decimal(510) - Decimal("0.65")
        # mark at last 6.00 -> position value 600
        q2 = Quote(opt, Decimal("5.9"), Decimal("6.1"), Decimal("6.0"), CLOCK.now())
        equity = sb.equity(MarketSnapshot({opt.key: q2}))
        assert equity == sb.cash() + Decimal(600)


async def test_end_to_end_performance(tenant_ctx: TenantId) -> None:
    async with UnitOfWork() as uow:
        led = EventLedger(uow.session, CLOCK)
        sb = SandboxLedger(led, "sub-4", starting_cash=Decimal(10_000), clock=CLOCK)
        sb._slippage.adjust = lambda price, order: price  # type: ignore[method-assign]
        sb._commission.fee = lambda order, price: Decimal(0)  # type: ignore[method-assign]
        snap = _snapshot("100", "100", "100")  # flat book for clean numbers
        await sb.submit(Order(AAPL, Side.BUY, Decimal(10)), snap)
        up = _snapshot("110", "110", "110")
        await sb.submit(Order(AAPL, Side.SELL, Decimal(10)), up)
        await sb.mark_to_market(up)

        events = await led.replay("sub-4")
        rec = PerformanceCalculator().from_events(events, Decimal(10_000))
        assert rec.num_trades == 1
        assert rec.win_rate == Decimal("1.0000")
        assert rec.net_pnl == Decimal(100)  # bought 1000, sold 1100

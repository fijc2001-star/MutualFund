"""Derive performance metrics by replaying a stream's ledger events (REQUIREMENTS §5.8).

Pure function of the events + starting cash — reproducible. Uses `fill` events for
realized trade stats and `mark` events (equity snapshots) for the equity curve.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal

from .event import LedgerEvent, LedgerEventType

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    starting_cash: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    num_trades: int
    win_rate: Decimal
    sharpe: Decimal | None


def _d(value: object) -> Decimal:
    return Decimal(str(value))


class PerformanceCalculator:
    def from_events(
        self, events: list[LedgerEvent], starting_cash: Decimal
    ) -> PerformanceRecord:
        # --- realized trade stats from fills (average-cost) ---
        qty_by_key: dict[str, Decimal] = {}
        avg_by_key: dict[str, Decimal] = {}
        total_fees = ZERO
        closes = 0
        wins = 0

        for ev in events:
            if ev.event_type is not LedgerEventType.FILL:
                continue
            p = ev.payload
            key = str(p["instrument"])
            side = str(p["side"])
            qty = _d(p["quantity"])
            price = _d(p["price"])
            fee = _d(p["fee"])
            mult = _d(p.get("multiplier", "1"))
            total_fees += fee

            pos = qty_by_key.get(key, ZERO)
            avg = avg_by_key.get(key, ZERO)

            if side == "buy":
                new_qty = pos + qty
                avg_by_key[key] = (pos * avg + qty * price) / new_qty if new_qty != 0 else ZERO
                qty_by_key[key] = new_qty
            else:  # sell — realize against average cost
                closed = min(qty, pos) if pos > 0 else qty
                gross = (price - avg) * closed * mult
                if gross - fee > 0:
                    wins += 1
                closes += 1
                qty_by_key[key] = pos - qty

        # --- equity curve from mark events ---
        equities = [
            _d(ev.payload["equity"])
            for ev in events
            if ev.event_type is LedgerEventType.MARK and "equity" in ev.payload
        ]

        if equities:
            net_pnl = equities[-1] - starting_cash
            max_dd = _max_drawdown_pct(equities)
            sharpe = _sharpe(equities)
        else:
            net_pnl = -total_fees
            max_dd = ZERO
            sharpe = None

        return_pct = (
            (net_pnl / starting_cash * Decimal(100)) if starting_cash != 0 else ZERO
        )
        win_rate = (Decimal(wins) / Decimal(closes)) if closes else ZERO

        return PerformanceRecord(
            starting_cash=starting_cash,
            net_pnl=net_pnl,
            return_pct=return_pct.quantize(Decimal("0.01")),
            max_drawdown_pct=max_dd.quantize(Decimal("0.01")),
            num_trades=closes,
            win_rate=win_rate.quantize(Decimal("0.0001")),
            sharpe=sharpe.quantize(Decimal("0.0001")) if sharpe is not None else None,
        )


def _max_drawdown_pct(equities: list[Decimal]) -> Decimal:
    peak = equities[0]
    max_dd = ZERO
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            dd = (peak - e) / peak * Decimal(100)
            max_dd = max(max_dd, dd)
    return max_dd


def _sharpe(equities: list[Decimal]) -> Decimal | None:
    if len(equities) < 3:
        return None
    returns: list[float] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev == 0:
            continue
        returns.append(float((equities[i] - prev) / prev))
    if len(returns) < 2:
        return None
    sd = statistics.pstdev(returns)
    if sd == 0:
        return None
    return Decimal(str(statistics.fmean(returns) / sd))

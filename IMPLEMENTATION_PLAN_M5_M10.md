# Implementation Plan — Phase 2: M10 Ledger + M5 Sandbox

> The trust + execution core. M5 runs a bot's orders into an isolated paper account; M10
> records every event immutably so performance is verifiable. Built together because the
> sandbox writes to the ledger and performance is *derived by replaying the ledger* — never
> edited. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §3.4/§3.7 and [`REQUIREMENTS.md`](./REQUIREMENTS.md) §1.5, §5.5.1, §5.8.1.

## Context
Phase 1 delivered Foundation + IAM + Market Data. The next dependency for everything
(qualification, marketplace track records, the live chart fed by real fills) is the ability
to (a) execute a bot's trades in a per-subscription sandbox and (b) record them in a
tamper-evident ledger that performance is computed from. This phase delivers both, headless
and fully tested — no UI, no live broker, no billing.

**Build order: M10 first, then M5** (the sandbox appends to the ledger, so the ledger must exist).

## New backend layout
```
backend/src/mutualfund/
  ledger/                # MODULE M10
    __init__.py
    models.py            # LedgerEntry (append-only, hash-chained) table
    event.py             # LedgerEvent value type + canonical serialization for hashing
    ledger.py            # EventLedger: append / verify / replay
    performance.py       # PerformanceCalculator -> PerformanceRecord
  execution/             # MODULE M5
    __init__.py
    orders.py            # Order, Side, OrderType, Fill, Position, MarketSnapshot
    venue.py             # ExecutionVenue protocol
    fills/               # the four pluggable models (REQUIREMENTS §5.5.1)
      __init__.py
      price.py           # FillPriceModel  (default: cross-the-spread)
      slippage.py        # SlippageModel   (default: fixed bps)
      commission.py      # CommissionModel (equities + per-contract options)
      options.py         # OptionsPricingModel (fill + mark-to-market)
    sandbox.py           # SandboxLedger: ExecutionVenue impl writing fills to the EventLedger
backend/tests/ledger/    backend/tests/execution/
```

## Phase A — M10: Event Ledger + Performance

### Tasks
- [ ] **`LedgerEvent`** (`event.py`): immutable value object — `stream_id`, `seq`, `event_type`
      (`signal` | `fill` | `param_set` | `mark`), `payload: dict`, `ts`. **Canonical
      serialization**: sorted-key JSON, `Decimal`→string, tz-aware ISO datetimes — so hashes
      are reproducible.
- [ ] **`LedgerEntry`** (`models.py`): tenant-scoped, append-only table. Columns: `stream_id`
      (index), `seq` (per-stream monotonic), `event_type`, `payload` (JSON), `ts`, `prev_hash`,
      `hash`. Unique `(stream_id, seq)`. No update/delete API.
- [ ] **`EventLedger`** (`ledger.py`):
  - `append(stream_id, event) -> LedgerEntry` — fetch last entry for the stream, compute
    `hash = sha256(prev_hash + canonical(event))`, persist with next `seq`.
  - `verify(stream_id) -> VerificationResult` — replay entries, recompute the chain, flag the
    first broken link. Detects any tampering (designer/insider/admin).
  - `replay(stream_id) -> Iterator[LedgerEvent]`.
- [ ] **`PerformanceCalculator`** (`performance.py`) → **`PerformanceRecord`**: derive from a
      stream's `fill`/`mark` events — realized + unrealized P&L, net return %, **max drawdown**,
      **trade count**, **win rate**, and **Sharpe** (from a periodic equity series; annualized).
      All `Decimal`. Pure function of the replayed events (reproducible).

### Tests (deterministic via `FixedClock`)
- [ ] Append builds a valid hash chain; `verify` passes on an intact chain.
- [ ] **Tamper detection**: mutate a stored payload → `verify` reports the break at the right seq.
- [ ] `seq` is per-stream monotonic; streams are isolated; cross-tenant access blocked.
- [ ] Performance math on a hand-built fill sequence: known P&L, drawdown, win rate, Sharpe.

**DoD:** ledger is append-only + tamper-evident; performance is reproducible from replay; mypy --strict clean; tests green.

## Phase B — M5: Execution / Sandbox

### Tasks
- [ ] **Domain types** (`orders.py`): `Side` (BUY/SELL), `OrderType` (v1: MARKET), `Order`
      (instrument, side, quantity, type), `Fill` (instrument, qty, price, fee, ts), `Position`
      (instrument, qty, avg_price), `MarketSnapshot` (quotes/marks keyed by instrument), all `Decimal`.
- [ ] **`ExecutionVenue`** protocol (`venue.py`): `submit(order, snapshot) -> Fill`,
      `positions()`, `cash()`, `equity(snapshot)`.
- [ ] **Four fill models** (`fills/`), each behind an interface, **admin-configurable via
      `Settings`**, conservative defaults:
  - `FillPriceModel` → cross-the-spread (buy@ask, sell@bid)
  - `SlippageModel` → fixed bps (configurable)
  - `CommissionModel` → equities (configurable, may be 0) + per-contract options fee
  - `OptionsPricingModel` → fill price + `mark()` for MTM (v1: from market snapshot quotes;
    Black-Scholes pluggable later)
- [ ] **`SandboxLedger`** (`sandbox.py`): an `ExecutionVenue` bound to a `stream_id` (one per
      `(user, bot)` subscription).
  - `submit`: compute fill via the four models → update cash + positions → **append a `fill`
    event to the `EventLedger`**.
  - Maintains materialized cash/positions; can be **rebuilt by replaying** the ledger
    (ledger is source of truth).
  - `mark_to_market(snapshot)`: append a `mark` event (equity snapshot) — feeds Sharpe/drawdown.
  - Provisioning helpers: `open(stream_id, starting_cash)` and `teardown(stream_id)` (REQUIREMENTS §1.5).
- [ ] **Config** (`config.py`): fill-model parameters (slippage bps, equity/option commissions,
      starting cash) with conservative defaults.

> **Risk seam:** orders submit directly in this phase. The `RiskModel`/`GuardrailPolicy` check
> (M6) is a documented integration point before `submit`, implemented later — not in this phase.

### Tests (deterministic via `FixedClock` + `FakeProvider` snapshots)
- [ ] Equity buy then sell: correct fill prices (cross-spread), commissions, cash, realized P&L.
- [ ] Options fill + mark-to-market across two snapshots (multiplier applied; greeks-agnostic v1).
- [ ] Every fill produces exactly one ledger `fill` event; positions rebuilt from replay match live state.
- [ ] Two subscriptions (different `stream_id`/tenant) stay fully isolated.
- [ ] End-to-end: feed a small signal→order sequence → sandbox fills → ledger → `PerformanceRecord`
      with expected metrics.

**DoD:** a bot's orders execute into an isolated sandbox with realistic fills, every event is on
the hash-chained ledger, and performance is derived from replay. ruff + mypy --strict clean; tests green.

## Sequencing & milestones
```
A. M10 EventLedger (+verify) ──► A. PerformanceCalculator ──► B. fill models ──► B. SandboxLedger ──► B. end-to-end
```
- **MA-1:** append-only hash-chained ledger + tamper test.
- **MA-2:** performance metrics from replay.
- **MB-1:** four fill models with conservative defaults.
- **MB-2:** SandboxLedger executes + writes ledger; positions rebuildable by replay.
- **MB-3:** signal→fill→ledger→performance end-to-end test.

## Verification
- `cd backend && & $py -m uv run ruff check . && & $py -m uv run mypy src && & $py -m uv run pytest -q`
  (`$py = C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`)
- New tests must cover: hash-chain integrity + tamper detection, fill correctness (equities +
  options MTM), per-subscription isolation, and reproducible performance.
- Optional manual: a script that runs a bot's order sequence through a `SandboxLedger` and prints
  the `PerformanceRecord` + `ledger.verify()` result.

## Out of scope (later phases)
- Live broker/exchange execution (`BrokerAdapter`), realtime streaming.
- M6 full risk engine, M4 qualification automation, marketplace/subscription provisioning + billing.
- Wiring the **real** sandbox to the web chart (follow-on once M5/M10 land — replaces the fake demo feed).
- Black-Scholes options pricing, historical options data vendor.

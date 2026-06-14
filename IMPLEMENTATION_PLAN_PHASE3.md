# Implementation Plan — Phase 3: Strategy + Signals + Risk + Qualification

> Turns the placeholder SMA bot into a **real, designer-composable, risk-guarded, qualifiable
> bot**. Modules M3 (Bot/Strategy), M9 (Signals), M6 (Risk & Sizing), M4 (Lifecycle &
> Qualification). See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §2–3 and [`REQUIREMENTS.md`](./REQUIREMENTS.md) §1.2.1, §5.4, §5.6, §5.8.

## Context
Phase 2 delivered the execution/trust core (M5 sandbox + M10 ledger) and we wired a built-in
SMA-crossover demo into the live chart. Two things are still hard-coded placeholders:
(1) the strategy logic lives in `realtime/sandbox_session.py`, and (2) orders skip any risk
check. This phase replaces both with real modules and adds the bot lifecycle + qualification
gate that the marketplace needs before a bot can be sold.

## Recommended order & how placeholders get replaced
```
M3/M9 (Strategy + Signals) ──► M6 (Risk + Sizing) ──► M4 (Lifecycle + Qualification)
```
- **After M3/M9:** the SMA logic becomes one `Strategy` implementation run by a `SignalEngine`
  against a stored `BotVersion` (immutable params). The sandbox session runs a *real bot*, not
  inline code.
- **After M6:** signals pass through `PositionSizer` + `RiskModel` + `GuardrailPolicy` before
  `sandbox.submit` — the seam left open in Phase 2.
- **After M4:** a bot has a lifecycle state machine and a pluggable, versioned qualification
  policy evaluated on the `PerformanceRecord` (M10), gating `Draft → Evaluation → Listed`.

---

## M3 — Bot & Strategy  (`backend/src/mutualfund/strategy/`)

**Purpose:** designer building blocks + immutable, versioned bot definitions.

- `strategy.py` — **`Strategy` protocol**: `evaluate(ctx: StrategyContext) -> list[Signal]`,
  plus `params_schema`. `StrategyContext` exposes recent bars/closes, indicators, and current
  position for one instrument/universe.
- `library/` — concrete strategies: **`SmaCrossStrategy`** (port the demo), **`MomentumStrategy`**;
  each declares a typed param schema (validated on publish).
- `registry.py` — **`StrategyRegistry`** (name → Strategy class) so bots reference strategies by id.
- `models.py` — **`Bot`** + **`BotVersion`** tables (tenant-scoped): version, `strategy_id`,
  frozen `params` (JSON), `universe`, `risk_profile_id`, `state`. **`BotRegistry.publish`** forks
  a *new* version (immutable history, REQUIREMENTS §5.8.1); params never edited in place.

**Tests:** strategy evaluates deterministically on a fixed bar series; param-schema validation
rejects bad params; publish creates a new immutable version; prior version unchanged.
**DoD:** a `BotVersion` + `Strategy` produce signals from market data, headless and tested.

---

## M9 — Signals  (`backend/src/mutualfund/signals/`)

**Purpose:** run a bot and produce ranked, explained signals.

- `signal.py` — **`Signal`** (instrument, action BUY/SELL/CLOSE, `strength`, **`Rationale`**:
  thesis, indicators fired, invalidation).
- `engine.py` — **`SignalEngine.run(bot_version, ctx) -> list[Signal]`**: instantiate the bot's
  `Strategy` with its params and evaluate.
- **Rewire** `realtime/sandbox_session.py` to: build a `BotVersion` (SMA) → `SignalEngine` →
  signals → (M6 sizing) → orders → sandbox. Stream the `Rationale` with each fill marker.

**Tests:** engine turns a known bar series into the expected signals + rationale; integrates with
the sandbox to produce the same fills the demo did.
**DoD:** the live chart runs a real `BotVersion` through the engine (no inline strategy code).

---

## M6 — Risk & Sizing  (`backend/src/mutualfund/risk/`)

**Purpose:** size signals into orders and enforce hard guardrails before execution.

- `sizing.py` — **`PositionSizer`** protocol + impls: `FixedQuantity`, `FixedFractional`
  (% of equity), `VolatilityTarget` (cap via recent stdev). Turns a `Signal` → order quantity.
- `model.py` — **`RiskModel.check(order, portfolio) -> RiskDecision`** (approve/reject + reason):
  max position %, sector/name concentration, options notional/leverage.
- `guardrails.py` — **`GuardrailPolicy.enforce(account) -> GuardrailState`**: global kill-switch,
  daily-loss limit, max drawdown — limits the agent/bot **cannot** override (REQUIREMENTS §5.6).
- Config: limits + sizing defaults (conservative) in `Settings`.
- **Integration:** in the sandbox path, `signal → PositionSizer → Order → RiskModel.check →
  (if approved) sandbox.submit`. Rejected orders are logged (audit) and surfaced, not executed.

**Tests:** sizing math (fixed/fractional/vol-target); risk rejects oversized/over-concentrated
orders; kill-switch + daily-loss block execution; approved orders flow through to a fill.
**DoD:** no order reaches the sandbox without passing sizing + risk; guardrails are hard.

---

## M4 — Lifecycle & Qualification  (`backend/src/mutualfund/lifecycle/`)

**Purpose:** the bot state machine + the gate that decides if a bot may be Listed/sold.

- `lifecycle.py` — **`BotState`** enum (`DRAFT→EVALUATION→LISTED→SUSPENDED/DELISTED→
  LIQUIDATION→RETIRED`) + **`BotLifecycle.transition(bot, to, reason)`** with an allowed-transition
  map; persists state on `BotVersion`; writes an audit/ledger record on each change.
- `qualification.py` — **`QualificationCriterion`** protocol + concrete criteria (min period,
  min trades, Sharpe floor, max-drawdown ceiling, net-positive, max concentration) reading a
  **`PerformanceRecord`** (M10). **`QualificationPolicy`** = named + versioned criteria set with
  `assess(perf) -> PolicyResult` (pass/fail + per-criterion reasons). Baseline values from
  REQUIREMENTS §5.8; admin-configurable.
- `service.py` — **`QualificationService`**: given a bot's sandbox `PerformanceRecord`, run the
  policy and transition `Evaluation→Listed` on pass, or flag `Suspended/Delisted` on breach.

**Tests:** state machine allows/blocks the right transitions; each criterion passes/fails on
crafted records; a passing record promotes Evaluation→Listed; a breaching one delists; policy is
versioned (the bar a bot passed is recorded).
**DoD:** a bot can be auto-evaluated against its sandbox performance and gated end-to-end.

---

## Integrated flow after Phase 3
```
market data → SignalEngine(BotVersion+Strategy) → Signal+Rationale
   → PositionSizer → Order → RiskModel.check / GuardrailPolicy
   → SandboxLedger.submit → fill → EventLedger (hash-chained)
   → PerformanceCalculator → QualificationPolicy → BotLifecycle transition
   → streamed to the live chart (fills + rationale + perf + lifecycle state)
```

## Verification
- `cd backend && & $py -m uv run ruff check . && & $py -m uv run mypy src && & $py -m uv run pytest -q`
  (`$py = C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`)
- New tests per module (above) + an end-to-end test: a `BotVersion` runs through engine→sizing→
  risk→sandbox→ledger→performance→qualification with expected state transitions.
- Manual: the live chart shows real-bot fills with rationale, live P&L, and the bot's lifecycle
  state; rejected orders (e.g., tripped guardrail) appear as blocked, not filled.

## Out of scope (later)
- Designer/marketplace UI, subscriptions/billing, multi-bot orchestration.
- Live broker execution (`BrokerAdapter`), agent/copilot (M13), notifications (M15).
- Advanced strategies (options-income), tax logic, optimizer (M7).
- Per-risk-tier qualification policies (design the seam; ship the global baseline first).

## Suggested staging (could be separate commits/PRs)
1. **M3/M9** — strategy + signals + rewire sandbox session to a real `BotVersion`.
2. **M6** — sizing + risk + guardrails inserted before `submit`.
3. **M4** — lifecycle state machine + qualification policy + service.

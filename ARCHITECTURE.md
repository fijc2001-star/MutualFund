# MutualFund — Architecture: Modules & Interfaces

> Companion to [`REQUIREMENTS.md`](./REQUIREMENTS.md). Defines the **main modules** (bounded contexts) of the Python/FastAPI backend and the **core interfaces** that decouple them. Goal: start building against stable contracts.
>
> Guiding rule (§4): **the LLM reasons; deterministic code decides the numbers.** Quant/money modules expose plain, testable interfaces; the agent only *calls* them.

---

## 1. Layered overview

```
┌──────────────────────────────────────────────────────────────────┐
│  INTERFACE LAYER   API Gateway (REST + WebSocket, OpenAPI) · BFF   │
├──────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE      Agent/Copilot (LLM orchestration) · Signals     │
├──────────────────────────────────────────────────────────────────┤
│  PLATFORM/BUSINESS Identity&Access · Marketplace · Subscriptions   │
│                    & Billing · Admin/Config · Notifications        │
├──────────────────────────────────────────────────────────────────┤
│  TRADING DOMAIN    Bot/Strategy · Lifecycle&Qualification · Market │
│                    Data · Execution/Sandbox · Risk · Portfolio ·   │
│                    Backtesting · Performance&Ledger                │
├──────────────────────────────────────────────────────────────────┤
│  FOUNDATION        Instrument model · Persistence · Tenancy ·      │
│                    Audit · Config  (cross-cutting)                 │
└──────────────────────────────────────────────────────────────────┘
```

**Dependency rule:** higher layers depend on lower ones, never the reverse. The Trading Domain knows nothing about HTTP, billing, or the LLM. The Agent orchestrates domain modules through their interfaces but contains no quant/money logic.

---

## 2. Module map

| # | Module | Responsibility | Key interfaces it owns | Depends on |
|---|--------|----------------|------------------------|------------|
| M1 | **Identity & Access (IAM)** | OAuth/OIDC login (Authlib), sessions/JWT, users, RBAC roles, tenancy, root admin | `IdentityProvider`, `SessionManager`, `RoleService`, `TenantContext` | Foundation |
| M2 | **Market Data** | Quotes/bars/option chains; `Instrument` catalog | `MarketDataProvider`, `InstrumentCatalog` | Foundation |
| M3 | **Bot & Strategy** | Strategy building blocks; bot definition, parameters, **immutable versioning** | `Strategy`, `BotRegistry`, `BotVersion` | M2 |
| M4 | **Lifecycle & Qualification** | Bot state machine; pluggable qualification policy | `BotLifecycle`, `QualificationCriterion`, `QualificationPolicy` | M3, M10 |
| M5 | **Execution / Sandbox** | `ExecutionVenue` (sandbox now, broker later); per-subscription sandbox; pluggable fill models | `ExecutionVenue`, `SandboxLedger`, `BrokerAdapter`, `FillPriceModel`, `SlippageModel`, `CommissionModel`, `OptionsPricingModel` | M2 |
| M6 | **Risk & Sizing** | Per-trade/portfolio limits, vol sizing, hard guardrails | `RiskModel`, `PositionSizer`, `GuardrailPolicy` | M2 |
| M7 | **Portfolio Construction** | Optimizer with risk constraints | `PortfolioOptimizer` | M6 |
| M8 | **Backtesting** | OSS-framework-backed engine sharing the live code path. **Historical, in-house only** — a designer R&D tool, *not* the marketplace track-record source (see flow note §4). | `BacktestEngine`, `DataFeed` | M2, M3, M5, M6 |
| M9 | **Signals** | Run bots → produce ranked, explained signal streams | `SignalEngine`, `SignalStream`, `Signal` | M3, M5, M6 |
| M10 | **Performance & Ledger** | Append-only, **hash-chained** ledger; performance metrics; verification | `EventLedger`, `PerformanceCalculator`, `PerformanceRecord` | Foundation |
| M11 | **Subscriptions & Billing** | Subscriptions, Stripe Connect, payouts, commission split, dunning, lifecycle | `BillingProvider`, `SubscriptionService`, `PayoutService` | M1 |
| M12 | **Marketplace** | Catalog, discovery, search/rank, bot detail | `MarketplaceService`, `BotQuery` | M3, M4, M10, M11 |
| M13 | **Agent / Copilot** | LLM orchestration; explains signals; narratives; calls domain tools | `AgentOrchestrator`, `AgentTool`, `LLMClient` | M2,M6,M9,M10 (read-only-ish) |
| M14 | **Admin / Config** | Global config (commission %, premium, thresholds, fee bounds), moderation, kill-switch | `ConfigStore`, `ModerationService`, `KillSwitch` | M1 |
| M15 | **Notifications** | Alerts on new signals/fills | `NotificationChannel`, `Notifier` | M9, M11 |
| M16 | **API Gateway / BFF** | REST + WebSocket endpoints, auth middleware, OpenAPI, DTO mapping | (HTTP routers, WS hubs) | all above |
| X | **Foundation** (cross-cutting) | `Instrument` model, persistence/UoW, `TenantContext`, `AuditLog`, `Clock` | `Repository`, `UnitOfWork`, `AuditLog`, `Clock` | — |

---

## 3. Core domain interfaces (Python protocol sketches)

> Illustrative signatures to anchor the contracts — names/shapes will firm up in code. Use `typing.Protocol` or ABCs. All money/quant types use `Decimal`, never float.

### 3.1 Foundation — Instrument & cross-cutting

```python
class AssetClass(str, Enum):
    EQUITY = "equity"; OPTION = "option"  # FUTURE, CRYPTO, FX later

@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: AssetClass
    multiplier: Decimal = Decimal(1)        # options/futures contract multiplier
    expiry: date | None = None              # options/futures
    strike: Decimal | None = None           # options
    option_type: Literal["C", "P"] | None = None
    tick_size: Decimal = Decimal("0.01")

class Clock(Protocol):
    def now(self) -> datetime: ...          # injectable for backtests/sandbox

class AuditLog(Protocol):
    def record(self, event_type: str, actor: ActorRef, payload: dict) -> None: ...

class TenantContext(Protocol):
    @property
    def tenant_id(self) -> TenantId: ...     # enforced on every repo query
```

### 3.2 M2 — Market Data

```python
class MarketDataProvider(Protocol):                  # first impl: ThinkorSwim/Schwab
    def quote(self, ins: Instrument) -> Quote: ...
    def bars(self, ins: Instrument, tf: TimeFrame, start, end) -> list[Bar]: ...
    def option_chain(self, underlying: str, expiry: date | None) -> OptionChain: ...
    def stream(self, instruments: list[Instrument]) -> Iterator[Quote]: ...  # realtime
```

### 3.3 M3 — Strategy & Bot

```python
class Strategy(Protocol):                            # designer building block
    def on_data(self, ctx: StrategyContext) -> list[Order]: ...
    @property
    def params_schema(self) -> ParamSchema: ...

@dataclass(frozen=True)
class BotVersion:
    bot_id: BotId
    version: int
    strategy_id: str
    params: Mapping[str, Any]                         # frozen once published (§5.8.1)
    universe: list[Instrument]
    risk_profile_id: str

class BotRegistry(Protocol):
    def publish(self, draft: BotDraft) -> BotVersion: ...   # forks new version
    def get(self, bot_id: BotId, version: int | None = None) -> BotVersion: ...
```

### 3.4 M5 — Execution venue & pluggable fill models

```python
class ExecutionVenue(Protocol):                      # SandboxLedger | BrokerAdapter
    def submit(self, order: Order, account: AccountRef) -> Fill | OrderAck: ...
    def positions(self, account: AccountRef) -> list[Position]: ...
    def cash(self, account: AccountRef) -> Decimal: ...

class FillPriceModel(Protocol):
    def price(self, order: Order, mkt: MarketSnapshot) -> Decimal: ...   # default: cross-spread

class SlippageModel(Protocol):
    def adjust(self, price: Decimal, order: Order, mkt: MarketSnapshot) -> Decimal: ...  # default: fixed bps

class CommissionModel(Protocol):
    def fee(self, order: Order, fill_price: Decimal) -> Decimal: ...     # equities + per-contract options

class OptionsPricingModel(Protocol):
    def fill_price(self, ins: Instrument, mkt: MarketSnapshot) -> Decimal: ...
    def mark(self, ins: Instrument, mkt: MarketSnapshot) -> Decimal: ... # MTM between fills

# SandboxLedger composes the four models above + an EventLedger (M10)
```

### 3.5 M6 — Risk

```python
class RiskModel(Protocol):                           # asset-class-aware
    def check(self, order: Order, portfolio: Portfolio) -> RiskDecision: ...

class PositionSizer(Protocol):
    def size(self, signal: Signal, portfolio: Portfolio) -> Decimal: ...

class GuardrailPolicy(Protocol):
    def enforce(self, account: AccountRef) -> GuardrailState: ...        # kill-switch, daily loss
```

### 3.6 M9 — Signals

```python
@dataclass(frozen=True)
class Signal:
    bot_version: BotVersion
    instrument: Instrument
    action: Literal["BUY","SELL","CLOSE"]
    rationale: Rationale            # thesis, signals fired, risk metrics, sizing, invalidation
    created_at: datetime

class SignalEngine(Protocol):
    def run(self, bot: BotVersion, ctx: RunContext) -> list[Signal]: ...

class SignalStream(Protocol):
    def publish(self, signal: Signal) -> None: ...
    def subscribe(self, subscription: SubscriptionRef) -> Iterator[Signal]: ...
```

### 3.7 M10 — Tamper-resistant ledger & performance

```python
class EventLedger(Protocol):                         # append-only + hash-chained (§5.8.1)
    def append(self, event: LedgerEvent) -> LedgerEntry:   # returns entry w/ prev_hash + hash
    def verify(self, scope: LedgerScope) -> VerificationResult: ...     # detects tampering
    def replay(self, scope: LedgerScope) -> Iterator[LedgerEvent]: ...

class PerformanceCalculator(Protocol):
    def metrics(self, scope: LedgerScope) -> PerformanceRecord: ...     # Sharpe, maxDD, net, trades...
```

### 3.8 M4 — Lifecycle & qualification

```python
class BotState(str, Enum):
    DRAFT="draft"; EVALUATION="evaluation"; LISTED="listed"
    SUSPENDED="suspended"; DELISTED="delisted"; LIQUIDATION="liquidation"; RETIRED="retired"

class QualificationCriterion(Protocol):              # composable, pluggable
    def evaluate(self, perf: PerformanceRecord) -> CriterionResult: ...

class QualificationPolicy(Protocol):                 # named + versioned set of criteria
    name: str; version: int
    def assess(self, perf: PerformanceRecord) -> PolicyResult: ...      # pass/fail + reasons

class BotLifecycle(Protocol):
    def transition(self, bot_id: BotId, to: BotState, reason: str) -> None: ...
```

### 3.9 M1 — Identity & Access

```python
class IdentityProvider(Protocol):                    # Authlib OAuth/OIDC wrapper
    def begin_login(self, provider: str) -> RedirectUrl: ...
    def complete_login(self, provider: str, cb: CallbackParams) -> Identity: ...

class RoleService(Protocol):
    def roles_of(self, user_id: UserId) -> set[Role]: ...               # cumulative
    def require(self, user_id: UserId, permission: Permission) -> None:  # raises if denied

class Role(str, Enum):
    USER="user"; DESIGNER="designer"; ADMIN="admin"; ROOT_ADMIN="root_admin"
```

### 3.10 M11 — Subscriptions & Billing

```python
class BillingProvider(Protocol):                     # Stripe Connect adapter
    def charge_subscription(self, sub: Subscription) -> Charge: ...
    def split_and_payout(self, charge: Charge, designer: DesignerRef, commission_pct: Decimal) -> Payout: ...
    def handle_webhook(self, event: WebhookEvent) -> None: ...           # dunning, cancels

class SubscriptionService(Protocol):
    def subscribe(self, user: UserId, bot: BotId) -> Subscription:       # auto-provisions sandbox (M5)
    def cancel(self, sub_id: SubscriptionId) -> None: ...                # runs to period end
    def on_lapse(self, sub_id: SubscriptionId) -> None: ...              # honor-to-cycle-end rules
```

### 3.11 M13 — Agent / Copilot

```python
class AgentTool(Protocol):                           # wraps a domain capability for the LLM
    name: str; schema: JsonSchema
    def invoke(self, args: dict, principal: Principal) -> ToolResult: ...

class AgentOrchestrator(Protocol):
    def chat(self, principal: Principal, message: str, tools: list[AgentTool]) -> Iterator[Token]: ...
```

> The agent's power is bounded by the **tools** it's given and the caller's **RBAC** — it can only do what the principal is authorized to do. It never writes to the ledger or moves money directly; it calls M9/M10/M6 read paths and proposes actions.

---

## 4. Key cross-module flows

**Subscribe → live sandbox simulation:**
`MarketplaceService.subscribe` → `SubscriptionService.subscribe` (M11) → provisions a `SandboxLedger` (M5) for (user, bot) → `SignalEngine` (M9) runs the `BotVersion` → signals pass `RiskModel` (M6) → `SandboxLedger` auto-fills via the four fill models → every event lands in `EventLedger` (M10) → streamed to UI over WebSocket (M16) + chart annotations.

**Bot qualification:**
`SignalEngine` runs in `EVALUATION` → fills recorded in `EventLedger` (M10) → `PerformanceCalculator` → `QualificationPolicy.assess` (M4) → on pass, `BotLifecycle.transition(LISTED)`.

**Designer payout:**
`BillingProvider.charge_subscription` (M11) → if designer bot, `split_and_payout` with admin `commission_pct` from `ConfigStore` (M14) → audit (X).

**Backtest vs. forward-test vs. charting (responsibility split):**
- **Backtest (historical)** → `BacktestEngine` (M8), in-house, designer R&D only — **not** verified and **not** sold.
- **Forward-test (live)** → `SandboxLedger` (M5) running a `BotVersion` in `EVALUATION`/`LISTED`, recorded in `EventLedger` (M10) → **this is the verified, sellable track record** feeding `QualificationPolicy` (M4).
- **Charting** → TradingView Lightweight Charts in `/packages/web`, fed signals/fills over WebSocket (M16); a *display surface only* — never Pine Script, never TradingView.com execution.

---

## 5. Module boundaries & rules

- **Foundation knows nothing upward.** `Instrument`, `EventLedger`, `TenantContext`, `AuditLog` have no dependencies on business modules.
- **Trading Domain is HTTP-free and LLM-free.** It can run headless (backtests, sandbox) with no web or agent present.
- **One write-owner per aggregate.** Only M10 appends to the ledger; only M5 mutates sandbox positions; only M11 touches billing state.
- **Tenancy is enforced at the repository layer**, not per-feature — every query is scoped by `TenantContext`.
- **All four fill models + qualification criteria are pluggable** (Protocol + registry), selected via `ConfigStore` (M14).
- **The agent acts only through `AgentTool`s** gated by `RoleService` — no privileged backdoor.

---

## 6. Suggested build order (maps to MVP §12)

1. **Foundation** (X): `Instrument`, persistence/UoW, `TenantContext`, `AuditLog`, `Clock`.
2. **M1 IAM**: OAuth login (Google) + JWT/session + RBAC + root admin.
3. **M2 Market Data**: ThinkorSwim/Schwab `MarketDataProvider` + `InstrumentCatalog`.
4. **M10 Ledger** + **M5 Sandbox** (with the four fill models) — the trust/execution core.
5. **M3 Bot/Strategy** + **M6 Risk** + **M9 Signals** — make a bot produce fills into a sandbox.
6. **M4 Lifecycle & Qualification** + **M10 PerformanceCalculator**.
7. **M12 Marketplace** + **M11 Subscriptions** (Stripe test mode) → subscribe auto-provisions a sandbox.
8. **M16 API/WS** + **real-time chart** (Lightweight Charts) — the primary v0.1 visualization.
9. **M13 Agent/Copilot** (explanations, narratives) + **M15 Notifications**.
10. **M14 Admin/Config** console.
11. **M8 Backtesting** (OSS framework) — can trail the sandbox since the sandbox is the visible product.

---

## 7. Frontend module mirror (brief)

`/packages/core` (shared TS) mirrors the API contract: `auth`, `marketplace`, `subscriptions`, `signals` (WS), `sandbox`, `billing`, `admin`, plus generated OpenAPI types. `/packages/web` composes these into feature areas: Marketplace, Bot Detail, Designer Studio, Subscriber Dashboard (+ live chart), Copilot, Admin Console. No domain logic — presentation only (§9).

# MutualFund — Agentic Trading-Bot Marketplace

> **One-liner:** A SaaS marketplace where members design trading bots and sell their **signal streams** to a community. Users subscribe to free or paid bots; designers monetize their strategies; the platform takes a configurable cut. Institutional-grade *process* — risk management, research synthesis, plain-English reasoning — made accessible to the masses.
>
> Users keep their **own brokerage accounts**. The platform never custodies funds. Bots emit signals; users act on them (with approval) in their own accounts. Copilot, not autopilot.

---

## 1. Platform Model & Roles (the heart of the product)

This is a **two-sided marketplace**: bot **designers** on the supply side, signal **subscribers** on the demand side, with the **platform** intermediating and taking a fee.

### 1.1 Roles

| Role | Capabilities | How they're created |
|------|-------------|---------------------|
| **User** | Browse the bot marketplace. Subscribe to **free** bot signal streams at no cost, or subscribe to a **designer's paid** bot for a recurring fee. Connect own brokerage; act on signals (approve-to-execute). Manage subscriptions & billing. | Default role on signup. |
| **Designer** | Everything a User can do **plus**: design, backtest, publish, and version bots; price bot subscriptions; view earnings & subscriber analytics; receive payouts (minus platform commission). | A User **upgrades by paying a premium** (the "designer premium"). |
| **Admin** | Full platform access: manage users/roles, moderate bots, set global config (commission %, designer premium, limits), view all analytics, suspend bots/accounts, handle disputes/refunds. | Granted by an existing Admin / root admin. |
| **Root Admin** | A single **configurable** super-admin with ultimate authority (can create/revoke Admins, change any global setting, emergency kill-switch). Bootstrapped from config at deploy time. | Set via platform configuration (env/secret), not the UI. |

> Roles are **cumulative**: Designer ⊃ User capabilities; Admin ⊃ everything. A user can hold the highest role they qualify for.

### 1.2 Bots & Signal Streams

- A **Bot** is a published, versioned strategy that emits a **signal stream** (ranked, explained trade signals — entries, exits, sizing guidance).
- A **Subscription** links a User to a Bot's stream. Subscriptions are **free** or **paid** (recurring fee within platform-configured bounds).
- **On subscribe, the system auto-provisions a per-subscription sandbox** (see §1.5): an isolated paper-trading ledger that automatically plays the bot's trades so the subscriber sees a live simulation tailored to their own subscription start date.
- Users also receive signals + rationale in-app and via notification. **Live execution into a real brokerage/exchange is a later stage** (§1.5).

### 1.2.1 Bot Lifecycle

`Draft` → `Evaluation` → `Listed` → (`Suspended` / `Delisted`) → `Liquidation` → `Retired`

- **Draft:** designer builds, configures, and backtests; not visible to others.
- **Evaluation (probation):** bot runs live in sandbox and is **monitored over an admin-configurable period**; must clear **admin-configurable performance thresholds** (e.g., min track-record length, risk-adjusted return floor, max drawdown ceiling). Not yet subscribable by others.
- **Listed:** passed evaluation — appears in the marketplace and is subscribable. Performance keeps recording.
- **Suspended / Delisted:** falls below thresholds, violates policy, or designer premium lapses → **removed from *new* subscriptions**. **Existing subscribers are honored to the end of their current billing cycle (no refunds, no early cutoff)**, after which the subscription does not renew. The bot enters **Liquidation**.
- **Liquidation (wind-down):** no new subscriptions; existing subscriber sandboxes run only to the end of each subscriber's billing cycle. When a subscriber's cycle ends, **that subscriber's sandbox ceases to exist** — open simulated positions are liquidated/closed and the sandbox (ledger + positions) is torn down (subject to audit-log retention, §5.11).
- **Retired:** once the last subscriber cycle has ended and all sandboxes are torn down, the bot is fully retired.

### 1.3 Monetization (all rates configurable by Admin)

The platform earns from **two revenue streams**: (1) the **designer access** premium, and (2) **bot subscriptions**.

| Lever | Description | Configurable? |
|-------|-------------|---------------|
| **Designer premium** | **Recurring** fee a User pays to hold the Designer role. | ✅ global |
| **Bot subscription fee** | Recurring fee, per user per bot. Set by the bot's creator within Admin-defined min/max. | ✅ per bot (bounded) |
| **Revenue split on subscriptions** | **Admin/platform-created bot → platform keeps 100%.** **Designer-created bot → platform keeps a configurable % (admin variable); designer receives the remainder.** | ✅ global % for designer bots |
| **Free bots** | Zero-fee streams (platform-provided starter bots and/or designer free tiers) to drive adoption. | n/a |
| **Platform tier (freemium)** | A platform-level subscription **separate from bot fees**, monetizing *capabilities*. **Free** tier (free bots, limited sandboxes, possibly delayed signals) vs. paid **Pro** tier (real-time signals, more concurrent subscriptions, full copilot, advanced analytics). Offsets LLM/compute cost and monetizes browsers who don't buy paid bots. | ✅ tier definitions admin-configurable |

> **Note:** The all-access bundle ("Netflix" model) and usage-metered billing are deferred (payout-splitting / metering complexity); revisit later. The freemium tier is **designed-in but likely lands in v1.x**, after the core marketplace ships.

- **Payments & payouts** flow through a marketplace-capable processor (**Stripe Connect** recommended): platform charges subscribers; for designer bots it retains the configured commission and pays out the designer; for platform/admin bots it retains the full subscription.

**Subscription lifecycle (applies to designer premium AND bot subscriptions):**
- **Involuntary stop (payment fails / card declines):** after dunning retries, access **lapses** — designer premium lapse suspends publishing/earning; bot-subscription lapse stops the signal stream.
- **Voluntary cancellation:** access **remains in effect until the end of the current paid period**, then does not renew.
- **Designer premium lapse / bot delisting → their bots' existing subscribers** are **honored to the end of each subscriber's current billing cycle (no refunds)**; only *new* subscriptions are blocked.

### 1.4 Trust & discovery (marketplace essentials)

- **Verified performance:** every bot shows transparent, tamper-resistant track record — backtest *and* forward/live signal performance, clearly labeled. No cherry-picking.
- **Marketplace discovery:** browse/search/rank bots by strategy type, asset class, risk profile, live performance, subscriber count, rating.
- **Moderation:** Admins review/suspend bots; designers can't retroactively edit history.

### 1.5 Execution Stages (sandbox now, live later)

The platform is built around an **`ExecutionVenue`** abstraction so the same bot signals can target a simulated ledger today and a real market later — without rewrites.

**Stage 1 — Per-subscription sandbox (v1):**
- On each subscription, auto-provision an **isolated sandbox** for the (user, bot) pair with its **own ledger**.
- The bot's trades **execute automatically** into that sandbox; the subscriber watches a live simulation seeded from their subscription start.
- **Each user has their own trade queue, position ledger, and historical record** per subscription — fully isolated from other users and from the designer's own run.
- This doubles as the trust/verification substrate: a bot's listed track record is its sandbox performance.
- **Teardown:** a subscriber's sandbox lives for the life of the subscription. When the subscription ends — including when a bot is in **Liquidation** (§1.2.1) and the subscriber's billing cycle lapses — the sandbox's open positions are liquidated and the sandbox (ledger + positions) **ceases to exist**, retained only as needed for the audit log.

**Stage 2 — Live exchange/broker execution (later):**
- The system is **designed to integrate with real exchanges/brokers** to connect a bot to a live market.
- Implemented as additional `ExecutionVenue` / `BrokerAdapter` implementations; the marketplace, sandbox, roles, and billing layers are untouched.
- Live execution reintroduces explicit **human-in-the-loop approval** and the hard risk guardrails before any real order is placed (gated behind legal sign-off, §11).

---

## 2. Product Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Business model** | **Bot-marketplace SaaS (Option B)** | Two-sided market; users trade their own accounts; platform never custodies funds. |
| **Roles** | **User / Designer / Admin (+ configurable Root Admin)** | Designer role gated by a premium; Admin fully privileged. |
| **Revenue** | (1) **Recurring designer premium** + (2) **bot subscriptions** — platform keeps **100%** of admin/platform bots and a **configurable %** of designer bots | Admin-tunable. |
| **Asset classes (v1)** | **US equities + options** | Deepest data, broadest broker API support. |
| **Asset classes (design goal)** | **Asset-class-agnostic core** | Add futures, crypto, forex without rewrites. |
| **Target user** | **Active traders** (subscribers) + **strategy creators** (designers) | Two-sided. |
| **Autonomy (v1)** | **Auto-simulated in a per-user sandbox** | On subscribe, each user gets an isolated paper-trading sandbox + ledger that **auto-executes** the bot's trades for simulation. **Live exchange execution is a designed-for-later stage.** |
| **Bot qualification** | **Evaluation period + thresholds** | A new bot must be monitored over an **admin-configurable period** and clear **performance thresholds** before other users may subscribe. |

---

## 3. What We Sell (and what we do NOT promise)

- **We sell:** a marketplace for institutional-grade *process and access* — disciplined risk controls, portfolio construction, research synthesis, transparent track records, and plain-English reasoning, at a fraction of institutional cost.
- **We do NOT promise:** specific returns or "beating the market." Neither the platform nor designers may guarantee performance. The defensible value is **better process, transparency, and access** — not guaranteed alpha.

---

## 4. Core Architectural Principle

> **The LLM reasons and communicates. Deterministic code decides the numbers.**

The agent is the **interface + orchestration + reasoning** layer. All quantitative decisions (risk sizing, optimization, backtests, options greeks, P&L, performance attribution) run in **deterministic, testable engines** that the agent *calls as tools*. Keeps math auditable, repeatable, and safe.

> **Everything runs in the Python backend.** The web/mobile clients are thin presentation layers — no trading, strategy, risk, broker, billing, or role logic ever runs in the frontend.

```
        ┌───────────────────────────────────────────────────────┐
        │   User (subscriber)   Designer (creator)   Admin        │
        └───────┬───────────────────┬──────────────────┬─────────┘
                │  subscribe/act     │ design/publish   │ configure/moderate
        ┌───────▼────────────────────▼──────────────────▼─────────┐
        │                   PLATFORM (Python / FastAPI)             │
        │  AuthZ & Roles │ Marketplace │ Subscriptions │ Billing &  │
        │  (RBAC)        │ & Discovery │ & Payouts      │ Commission │
        ├───────────────────────────────────────────────────────────┤
        │              AGENT ORCHESTRATION (LLM, tool-calling)       │
        ├──────┬─────────┬──────────┬──────────┬─────────┬──────────┤
        │Market│ Risk &  │ Portfolio│ Bot /    │ Backtest│ Execution│
        │ Data │ Sizing  │ Optimizer│ Strategy │ & Perf  │ (broker  │
        │      │ Engine  │          │ Engine   │ Tracking│ adapters)│
        └───┬──┴────┬────┴────┬─────┴────┬─────┴────┬────┴────┬─────┘
        ┌───▼───────▼─────────▼──────────▼──────────▼─────────▼─────┐
        │   ASSET-CLASS ABSTRACTION (Instrument interface)          │
        │   Equity | Option | (Future | Crypto | FX ...)            │
        └──────────────────────────────────────────────────────────┘
```

---

## 5. Functional Requirements

### 5.1 Accounts, Roles & Authorization
- **Authentication: in-house, social-first.** OIDC/OAuth login via **Authlib** (Google first; designed for multiple providers — Apple/Microsoft/GitHub). After the provider callback, the backend issues its **own JWT/session** and manages its lifetime, refresh, revocation, and logout. Email/magic-link fallback only if non-social users are needed.
- **Account linking:** same identity across providers (matched by verified email) maps to one account, per a defined linking policy.
- **Do not hand-roll the OAuth protocol** — use Authlib (state/PKCE/token exchange).
- Signup defaults to **User**. Role upgrade to **Designer** via paid premium; **Admin** granted by Admin/root admin.
- **Role-based access control (RBAC)** owned and enforced **server-side** on every request; cumulative privileges. (Authentication = who you are via OAuth; authorization = what you can do, always in FastAPI.)
- **Root admin** bootstrapped from configuration (env/secret), not editable via normal UI.

### 5.2 Brokerage Integration
- Connect user's own brokerage via API (**v1: Alpaca**; `BrokerAdapter` interface for IBKR, Tradier, etc.).
- Read positions/balances/buying power/orders; place/modify/cancel **only after explicit user approval** (v1).
- **Paper-trading is first-class** and the onboarding default.

### 5.3 Marketplace & Discovery
- Browse/search/filter/rank bots by asset class, strategy type, risk, **live performance**, subscribers, rating.
- Bot detail page: description, strategy summary, **verified backtest + live track record**, fee, designer profile.
- Subscribe / unsubscribe; manage active subscriptions.

### 5.4 Bot Design (Designer role)
- Create, configure, **backtest**, publish, and **version** bots.
- Define which `Strategy` building blocks the bot uses, parameters, asset universe, risk profile.
- Set subscription price (within Admin bounds); free tier optional.
- Earnings dashboard: subscribers, revenue, payouts, commission deducted.
- Published bot history is **immutable** (no retroactive performance editing).

### 5.5 Signal Streams, Sandbox Simulation & Copilot
- Subscribed bots deliver **ranked, explained signals**: thesis, signals fired, risk metrics, sizing logic, invalidation conditions.
- **Per-subscription sandbox:** on subscribe, auto-provision an isolated paper-trading ledger for the (user, bot) pair that **auto-executes** the bot's trades. Each user has their own **trade queue, positions, ledger, and historical record**, isolated per subscription.
- Subscriber dashboards: live simulated P&L, open positions, trade history, and performance vs. the bot's headline track record.
- **Real-time signal/position chart (MVP focus):** the bot's generated signals and sandbox position changes render as **live annotations on a TradingView Lightweight Charts** view — price action with buy/sell markers (▲/▼), entry/exit price lines, and current position state — updated in real time over WebSocket. (This is the initial visualization goal: *see the bot's signals and position changes play out on the chart live.*)
- Conversational copilot: "explain this signal", "what's my risk today", portfolio narrative ("what moved and why").
- Notifications on new signals/fills.

#### 5.5.1 Sandbox Fill Model (pluggable)

The sandbox's realism is governed by **four independent, pluggable models** behind interfaces, so each dimension can be swapped or extended later without touching the rest. Each is **admin-configurable**, and the platform ships **deliberately slightly-conservative defaults** (under-promising in simulation protects users when they later go live).

| Dimension | Interface | v1 default | Future extensions (pluggable) |
|-----------|-----------|-----------|-------------------------------|
| **Fill price** | `FillPriceModel` | **Cross-the-spread** (buy at ask, sell at bid) | last/mid price, next-bar open, VWAP, etc. |
| **Slippage** | `SlippageModel` | **Fixed bps** (configurable) | volume/volatility-based, market-impact models |
| **Commissions/fees** | `CommissionModel` | **Modeled** — equities (configurable, may be $0) + **per-contract options fees** | tiered/broker-specific schedules |
| **Options pricing** | `OptionsPricingModel` | **Real historical options quotes** (data vendor, see §13) | Black-Scholes / model-based pricing from underlying + IV |

- All four are selected per-environment via config; the chosen models and parameters are **recorded with each fill** in the audit log so any track record is fully reproducible.
- Options require **mark-to-market between fills** (greeks move continuously); the `OptionsPricingModel` supplies both fill and MTM prices.

### 5.6 Risk & Position Sizing Engine (deterministic)
- Per-trade & per-portfolio limits: max position %, sector concentration, max drawdown, options notional/leverage.
- Volatility-aware sizing (vol targeting / fractional Kelly cap).
- Options risk: greeks aggregation, assignment risk, expiry exposure.
- **Hard guardrails** the agent/bot cannot override (kill-switch, daily loss limit). Apply to each user's own account.

### 5.7 Portfolio Construction (deterministic)
- Optimizer (mean-variance / risk-parity) with risk-engine constraints.
- Tax-awareness hook (lot selection, wash-sale flags) — design now, deepen later.

### 5.8 Backtesting, Performance Tracking & Bot Qualification
- Backtest framework sharing the **same code path** as sandbox/live (no drift). The backtest engine runs **in the Python `core`** so track records are deterministic, replayable, and fed into the tamper-resistant ledger (§5.8.1).
  - **MVP accelerator:** rather than building a backtester from scratch, adopt a **free open-source Python framework** (e.g., **backtesting.py** for speed-to-ship, or VectorBT/Backtrader as needs grow), wrapped in `core`. Evolve toward a bespoke engine over time without changing the architecture.
  - **TradingView backtester is *not* used:** it has **no public API** to run Pine Script backtests or extract results programmatically — it cannot feed a verifiable, multi-tenant marketplace. Designers may prototype in TradingView manually, but **platform track records come only from the in-core engine + sandbox.**
  - TradingView is leveraged for **charting only** — Lightweight Charts + free embeddable Widgets (§8).
- **Forward/sandbox performance recording** per bot — the basis for marketplace trust; tamper-resistant.
- **Bot qualification gate:** during the `Evaluation` lifecycle stage, a bot is monitored over an **admin-configurable period** and must clear a **qualification policy** before it can be `Listed` / subscribed to by other users.
- **Pluggable qualification policy:** the gate is a composable set of **`QualificationCriterion`** rules behind an interface — new criteria can be added, removed, or swapped without code changes elsewhere. The policy is **named and versioned**, so the exact bar a given bot passed is always recorded even as the rules evolve. v1 baseline (global defaults, admin-editable, designed to later vary **per risk tier**), bot must pass **all**:

  | Criterion | Guards against | v1 default |
  |-----------|----------------|-----------|
  | Min evaluation period | Lucky short streaks | **90 days** live in sandbox |
  | Min closed trades | Tiny-sample flukes | **≥ 30** |
  | Risk-adjusted return (Sharpe) | Luck/leverage masquerading as skill | **≥ 1.0** annualized |
  | Max drawdown ceiling | Blow-up-prone strategies | **≤ 25%** peak-to-trough |
  | Profitability floor | Net-losing strategies | **Positive net return** after fees/slippage |
  | Max position concentration | One lucky bet carrying the record | **≤ 30%** of sandbox equity |

- **Continuous enforcement:** criteria are evaluated even after listing; a `Listed` bot that breaches them can be auto-flagged for `Suspended`/`Delisted` (§1.2.1).
- Listed bots are continuously evaluated; falling below thresholds can trigger `Suspended`/`Delisted` (§1.2.1).

#### 5.8.1 Tamper-Resistant Performance Verification

A bot's track record is the trust backbone of the marketplace and must be **provably untampered**.

- **Append-only event ledger:** every signal, fill, and parameter set is an immutable, append-only record — no UPDATE/DELETE. Performance is **derived by replaying the ledger**, never edited directly. The ledger is the single source of performance truth.
- **Hash-chaining:** each record carries the cryptographic hash of the previous one. Altering any past entry breaks every subsequent hash, so tampering — by a designer, insider, or admin — is instantly detectable.
- **Immutable in testing/evaluation:** a bot's **performance ledger recorded during `Evaluation` (testing mode) is immutable**, as are the **bot's parameters**. Performance is bound to the exact parameter set that produced it.
- **Immutable versioning:** changing a bot's parameters **forks a new bot version** with its own fresh track record; the prior version's history and parameters are frozen. A designer can never "fix" a strategy and keep the old record.
- **No cherry-picking:** a bot's public record starts at `Evaluation`/`Listed` and cannot be reset; abandoned/delisted bots remain on the designer's history (no spin-up-many-keep-the-winner gaming).
- **Future hook:** signed daily Merkle roots / external notarization (e.g., public timestamping) for an "even the platform can't backdate" guarantee — designed-for-later.

### 5.9 Billing, Subscriptions & Payouts
- Marketplace payments via **Stripe Connect** (recommended): charge subscribers, retain configurable commission, pay out designers.
- Designer premium billing.
- Admin configures commission %, designer premium, fee bounds.
- Invoices, refunds, dispute handling, dunning.

### 5.10 Admin Console
- Manage users/roles, moderate/suspend bots & accounts, set global config, view platform-wide analytics, handle disputes/refunds, emergency kill-switch.

### 5.11 Execution & Audit
- **`ExecutionVenue` abstraction:** Stage 1 = **sandbox ledger** (auto-execute, simulated); Stage 2 = **live broker/exchange** (`BrokerAdapter`, approval-gated) — same signal path, swappable venue.
- Smart order handling behind `BrokerAdapter` for the live stage.
- **Full audit log:** every signal, sandbox/real fill, approval, subscription, and payout recorded with rationale/state snapshot.

---

## 6. The Asset-Class Abstraction (key extensibility bet)

Common **`Instrument`** model + small interface set so adding an asset class is additive:

- `Instrument` — symbol, asset class, contract specs (multiplier, expiry, strike, tick size).
- `MarketDataProvider` — quotes/bars/chains per asset class. **First implementation: ThinkorSwim / Schwab API** (TD Ameritrade's API migrated to the Schwab Developer API; the same integration can later serve as a live `ExecutionVenue`). Fully **swappable** — any other provider (Polygon, Databento, etc.) plugs in behind the interface.
- `Strategy` — building blocks designers compose into bots; consumes `Instrument` data, emits signals.
- `RiskModel` — asset-class-aware risk (an option's risk ≠ an equity's).
- `ExecutionVenue` — where orders go: **`SandboxLedger`** (v1, simulated) or a live **`BrokerAdapter`** (later).
- `BrokerAdapter` — venue/broker/exchange-specific live order placement (a kind of `ExecutionVenue`).

> Adding **futures** or **crypto** later = implement these interfaces + an execution venue. Marketplace, roles, billing, agent, sandbox, and UI are untouched.

---

## 7. Non-Functional Requirements

- **Auditability:** every automated decision and money movement logged with inputs, rationale, outcome.
- **Determinism where it counts:** risk/optimization/backtest/performance math reproducible and unit-tested; LLM never in the numeric or money critical path.
- **Trust & integrity:** performance records tamper-resistant; published bot history immutable.
- **Safety-first defaults:** paper mode default, conservative limits, explicit approval, global kill-switch.
- **Multi-tenant isolation:** strict per-tenant/per-user data isolation enforced server-side.
- **Latency:** copilot interactive; signal generation batch/near-real-time (not HFT).
- **Data lineage:** cited sources for surfaced research.

---

## 8. Tech Stack (locked)

| Layer | Choice | Notes |
|-------|--------|-------|
| **Backend** | **Python + FastAPI** | Single source of truth: auth/RBAC, marketplace, billing, brokers, strategies, risk, agent orchestration. REST/JSON + WebSocket, OpenAPI. |
| **Frontend (web)** | **React + TypeScript SPA via Vite** | Pure client, clean FE/BE separation. No SSR (behind login). |
| **Mobile (later)** | **React Native + Expo** | Shares logic with web via `core`; UI rebuilt. |
| **Charts (price)** | **TradingView Lightweight Charts** + free **TradingView Widgets** | Web. Free. Widgets (advanced chart, mini-chart, ticker, screener) are drop-in embeds — used to accelerate the MVP. |
| **Charts (analytics)** | Recharts / visx | Performance, allocation, drawdown, greeks. |
| **Tables** | **TanStack Table** (+ virtualization) | Marketplace lists, positions, orders. |
| **Server state / fetching** | **TanStack Query** | Works web + RN. |
| **Client state** | **Zustand** | Works web + RN. |
| **Web UI kit** | **shadcn/ui + Tailwind** | Web only; mobile uses NativeWind. |
| **Agent chat UI** | **Vercel AI SDK** | Streaming + tool-call/approval rendering; points at FastAPI. |
| **Real-time** | **WebSocket** | Signals, quotes, fills, agent tokens. |
| **Payments** | **Stripe Connect** | Marketplace charges, commission split, designer payouts. |
| **Auth / tenancy** | **In-house auth** — OIDC/OAuth social login via **Authlib** (Google first, multi-provider), backend-issued **JWT/session**, **RBAC** in FastAPI | **Multi-tenant**; per-request isolation server-side. Social-first removes password risk; **don't hand-roll the OAuth protocol — use Authlib**. Email/magic-link fallback added only if non-social users are needed. |
| **LLM provider** | **Claude** | Tool-use + reasoning quality. |

---

## 9. Repository Structure (monorepo)

Monorepo via **pnpm + Turborepo**. Split protects the future mobile path: shared logic, not shared UI.

```
/packages
  /core      ← pure TS: API clients, types, WebSocket layer, domain logic
              (NO DOM / NO browser APIs — shared by web AND mobile)
  /web       ← Vite + React + shadcn/ui            (v1)
  /mobile    ← React Native + Expo                 (later; imports /core)
/backend     ← Python + FastAPI (platform + quant + agent core)
```

**Architectural rules:**
- Zero financial/trading/billing/role logic in any frontend; all of it in the Python backend.
- Frontend is a presentation client only.
- **Logic shared, presentation rebuilt** — mobile reuses `/core`, never web UI components.
- **No shared-UI frameworks for now** (no Tamagui/Solito); revisit only if mobile becomes primary.

---

## 10. Frontend ⟷ Backend Contract

- **REST/JSON** for request/response (marketplace, subscriptions, positions, orders, config, billing).
- **WebSocket** for streaming: live signals, quotes, fills, agent tokens.
- **OpenAPI**-generated typed clients consumed by `/packages/core`.
- Broker credentials, payment secrets, and role logic live **only** in the backend, never sent to clients.

---

## 11. Compliance & Legal (must resolve before going live — not before building)

> ⚠️ **Open item — requires a securities lawyer before real-money launch. The marketplace model raises the stakes versus a single-user tool.**

- **Designers selling trade signals for a fee may be acting as unregistered investment advisers** — and the platform may bear liability for facilitating it. This is the central legal question and must be assessed early.
- **No performance guarantees** by platform or designers in any marketing or UI copy.
- Marketplace requires: ToS for users *and* designers, risk disclosures, designer agreements, payout/tax handling (e.g., 1099s for US designers), refund/dispute policy.
- **KYC/AML** likely required for designer payouts (Stripe Connect handles much of this).
- Data/brokerage API terms compliance.
- **Build + paper-trade freely now; gate real-money execution and paid subscriptions behind legal sign-off.**

---

## 12. Suggested MVP Scope (v0.1)

1. Auth + **RBAC** with User/Designer/Admin roles and a config-bootstrapped **root admin**.
2. Market data + `Instrument` + `MarketDataProvider` + `ExecutionVenue` abstractions; **`SandboxLedger`** as the v1 execution venue.
3. **Bot design** (Designer): compose strategies, backtest, publish, version. 1–2 equity strategies + 1 options-income strategy as building blocks.
4. **Bot lifecycle + qualification gate**: Draft → Evaluation (admin-configurable period + thresholds) → Listed.
5. **Marketplace**: browse/subscribe to free bots; bot detail with verified track record.
6. **Per-subscription sandbox**: auto-provisioned isolated ledger that auto-executes the bot; subscriber dashboard (simulated P&L, positions, history).
7. **Signal streams + copilot**: explained signals, sandbox fills, daily narrative.
   - **Primary v0.1 visualization:** bot signals + position changes shown **live on a TradingView Lightweight Charts** view (▲/▼ markers, entry/exit lines, position state) streamed over WebSocket.
8. Deterministic risk/sizing engine with hard guardrails.
9. **Billing skeleton**: Stripe Connect integration for paid subscriptions, configurable commission, designer premium, payouts. *(Can run in test mode for v0.1.)*
10. **Admin console**: manage roles, moderate bots, set commission/premium/qualification thresholds, kill-switch.
11. Full audit log.

**Out of scope for v0.1:** live exchange/broker execution, full autonomy, futures/crypto/FX (interfaces only), tax-optimization depth, mobile app, advanced ratings/social features.

---

## 13. Decision Log

All decisions below are **locked** and documented in the referenced sections — this is a quick index, not the source of truth.

| Decision | Choice | Section |
|----------|--------|---------|
| Product shape | Two-sided **bot marketplace** (User / Designer / Admin + root admin) | §1, §2 |
| Business model | **SaaS (Option B)** — users trade own accounts; platform never custodies funds | §2 |
| Revenue | Recurring **designer premium** + bot subscriptions; platform keeps **100% of admin bots**, **configurable %** of designer bots | §1.3 |
| Subscription lifecycle | Failed payment → lapse after dunning; cancel → runs to period end; delisted bot → existing subs honored to end of cycle, no refunds | §1.2.1, §1.3 |
| v1 execution | **Per-subscription sandbox** (auto-executed simulated ledger); live broker/exchange is a later stage via `ExecutionVenue` | §1.5, §5.11 |
| Sandbox fill model | Four pluggable models (`FillPriceModel`, `SlippageModel`, `CommissionModel`, `OptionsPricingModel`); conservative admin-configurable defaults | §5.5.1 |
| Real-time visualization | Bot signals + position changes live on **TradingView Lightweight Charts** over WebSocket (primary v0.1 view) | §5.5 |
| Bot lifecycle & qualification | `Draft → Evaluation → Listed → Suspended/Delisted → Liquidation → Retired`; pluggable, versioned **`QualificationCriterion`** policy (baseline: ≥90d, ≥30 trades, Sharpe ≥1.0, maxDD ≤25%, net+, conc ≤30%) | §1.2.1, §5.8 |
| Performance verification | Append-only **hash-chained** ledger; immutable evaluation-mode results + parameters; **immutable versioning**; no cherry-picking | §5.8.1 |
| Backtesting | In-core Python engine, accelerated by an **OSS framework** (backtesting.py / VectorBT / Backtrader); TradingView backtester **not integrable** | §5.8 |
| Platform tier | **Freemium** Free/Pro (capability-based, admin-configurable); bundle & metering deferred | §1.3 |
| Data source | **ThinkorSwim / Schwab API** first behind swappable `MarketDataProvider`; options-data vendor possible later | §6 |
| Auth | **In-house**, OIDC/OAuth social login via **Authlib** (Google first); backend JWT/session; **RBAC in FastAPI** | §5.1 |
| Tech stack | **Python/FastAPI** backend + **Vite/React/TS** web + **Expo** mobile (later); pnpm/Turborepo monorepo | §8, §9 |
| Tenancy | **Multi-tenant** from day one | §8 |
| LLM provider | **Claude** | §8 |
| Payments | **Stripe Connect** (marketplace) | §8 |
| Designer eligibility | **Open to anyone who pays the recurring premium**; quality controlled at the **bot level** via the qualification gate, not by gatekeeping people | §1.2.1 |

### Still open / deferred (not blocking v0.1)
- [ ] Concrete **legal review** before real-money launch (§11) — the central pre-launch gate.
- [ ] Historical **options data vendor** (Polygon/Databento) if/when historical options backtesting is needed.
- [ ] **Account-linking** policy specifics across OAuth providers.

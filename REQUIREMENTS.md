# Mutual_Fund — Agentic Trading Copilot

> **One-liner:** An AI trading copilot that brings institutional-grade *process* — risk management, portfolio construction, and research synthesis — to active retail traders, delivered as SaaS. Users keep their own brokerage accounts; the app reasons, proposes, and (on approval) executes.

---

## 1. Product Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Business model** | **Option B — SaaS, not a managed fund** | Users connect *their own* brokerage accounts. We never custody funds. Avoids becoming a regulated fund; ships with a small team. |
| **Asset classes (v1)** | **US equities + options** | Deepest data, broadest broker API support. |
| **Asset classes (design goal)** | **Asset-class-agnostic core** | Architecture must add futures, crypto, forex, etc. without rewrites. |
| **Target user** | **Active trader wanting an AI copilot** | Not "set-and-forget." Wants speed, rationale, and control — copilot, not autopilot. |
| **Autonomy level (v1)** | **Human-in-the-loop** | Agent proposes → user approves → app executes. Architected so full-auto is "remove the approval gate" later. |

---

## 2. What We Sell (and what we do NOT promise)

- **We sell:** institutional-grade *process and access* — disciplined risk controls, portfolio construction, research synthesis, and plain-English reasoning, at a fraction of institutional cost.
- **We do NOT promise:** specific returns or "beating the market." Performance claims are a legal and credibility trap. The defensible value is **better process, less emotion, faster research** — not guaranteed alpha.

---

## 3. Core Architectural Principle

> **The LLM reasons and communicates. Deterministic code decides the numbers.**

The agent is the **interface + orchestration + reasoning** layer. All quantitative decisions (risk sizing, optimization, backtests, options greeks, P&L) run in **deterministic, testable engines** that the agent *calls as tools*. This keeps math auditable, repeatable, and safe — and keeps the LLM doing what it's good at: synthesis and explanation.

> **Note:** the agent orchestration layer and *all* engines below run in the **Python backend**. The web/mobile clients are thin presentation layers — no trading, strategy, risk, or broker logic ever runs in the frontend.

```
        ┌─────────────────────────────────────────────┐
        │                 User (active trader)         │
        └───────────────┬─────────────────────────────┘
                        │  chat / approve / configure
        ┌───────────────▼─────────────────────────────┐
        │            AGENT ORCHESTRATION LAYER          │
        │   (LLM: plans, explains, calls tools)         │
        │   - intent → portfolio policy                 │
        │   - "why this trade" narration                │
        │   - news/filings synthesis                    │
        └───┬───────┬───────┬───────┬───────┬───────────┘
            │       │       │       │       │   (tool calls)
   ┌────────▼─┐ ┌───▼────┐ ┌▼──────┐ ┌▼─────┐ ┌▼──────────┐
   │ Market   │ │ Risk & │ │Portfolio│ │Strat-│ │ Execution │
   │ Data     │ │ Sizing │ │ Optimizer│ │egy / │ │ (broker   │
   │ Service  │ │ Engine │ │          │ │Signal│ │ adapters) │
   └────┬─────┘ └───┬────┘ └────┬────┘ └──┬───┘ └─────┬─────┘
        │           │           │         │           │
   ┌────▼───────────▼───────────▼─────────▼───────────▼─────┐
   │   ASSET-CLASS ABSTRACTION (Instrument interface)        │
   │   Equity | Option | (Future | Crypto | FX ...)          │
   └────────────────────────────────────────────────────────┘
```

---

## 4. Functional Requirements

### 4.1 Account & Broker Integration
- Connect user's own brokerage via API (**v1: Alpaca** for equities/options; design a **`BrokerAdapter` interface** so Interactive Brokers, Tradier, etc. plug in).
- Read: positions, balances, buying power, order status.
- Write: place / modify / cancel orders (only after explicit user approval in v1).
- **Paper-trading mode is first-class** — must be the default for onboarding, demos, and backtest-to-live parity.

### 4.2 Agent Copilot
- Conversational interface: "what's my risk today?", "find me momentum setups in semis", "should I roll this call?"
- Every trade proposal includes a **structured rationale**: thesis, signals fired, risk metrics, position size logic, and what would invalidate it.
- Synthesizes news, earnings, and filings into a thesis with sources cited.
- Daily / on-demand portfolio narrative: "what moved and why."

### 4.3 Strategy & Signal Engine
- Pluggable strategies (**`Strategy` interface**): momentum, mean-reversion, factor screens, options income (covered calls, spreads) to start.
- Strategies emit **ranked, explained signals** — never silent orders.
- Backtesting framework with the **same code path** as live (no logic drift between sim and real).

### 4.4 Risk & Position Sizing Engine (deterministic)
- Per-trade and per-portfolio limits: max position %, sector concentration, max drawdown, max options notional/leverage.
- Volatility-aware sizing (e.g., volatility targeting / fractional Kelly cap).
- Options-specific risk: greeks aggregation, assignment risk, expiry exposure.
- **Hard guardrails** that the agent cannot override (kill-switch, daily loss limit).

### 4.5 Portfolio Construction (deterministic)
- Optimizer: mean-variance / risk-parity options, with constraints from the risk engine.
- Tax-awareness hook (e.g., lot selection, wash-sale flags) — design now, deepen later.

### 4.6 Execution
- Smart order handling (limit logic, slippage awareness) abstracted behind `BrokerAdapter`.
- Full audit log: every proposal, approval, and fill is recorded with the rationale snapshot.

---

## 5. The Asset-Class Abstraction (the key extensibility bet)

Everything trades through a common **`Instrument`** model and a small set of interfaces so adding an asset class is additive, not invasive:

- `Instrument` — symbol, asset class, contract specs (multiplier, expiry, strike, tick size).
- `MarketDataProvider` — quotes/bars/chains per asset class.
- `Strategy` — consumes `Instrument` data, emits signals.
- `RiskModel` — asset-class-aware risk (an option's risk ≠ an equity's).
- `BrokerAdapter` — venue/broker-specific order placement.

> Adding **futures** or **crypto** later = implement these interfaces for the new class + a broker adapter. The agent, risk framework, and UI are untouched.

---

## 6. Non-Functional Requirements

- **Auditability:** every automated decision is logged with inputs, rationale, and outcome. This is both a trust feature and a compliance necessity.
- **Determinism where it counts:** risk/optimization/backtest math is reproducible and unit-tested; the LLM is never in the numeric critical path.
- **Safety-first defaults:** paper mode default, conservative limits, explicit approval, global kill-switch.
- **Latency:** copilot responses interactive; signal generation can be batch/near-real-time (active trading, not HFT — we are not competing on microseconds).
- **Data lineage:** cited sources for any research the agent surfaces.

---

## 7. Tech Stack (locked)

| Layer | Choice | Notes |
|-------|--------|-------|
| **Backend** | **Python + FastAPI** | Single source of truth: auth, brokers, strategies, risk, agent orchestration. Exposes REST/JSON + WebSocket, documented via OpenAPI. |
| **Frontend (web)** | **React + TypeScript SPA via Vite** | Pure client, no server layer — gives clean frontend/backend separation. No SSR (irrelevant behind login). |
| **Mobile (later)** | **React Native + Expo** | Shares logic with web via the `core` package; UI is rebuilt (logic shared, presentation rebuilt). |
| **Charts (price)** | **TradingView Lightweight Charts** | Web. Industry default for candlestick/OHLC; free (MIT). |
| **Charts (analytics)** | Recharts / visx | Allocation, drawdown, greeks. |
| **Tables** | **TanStack Table** (+ virtualization) | Positions/orders grids. |
| **Server state / fetching** | **TanStack Query** | Works web + RN. |
| **Client state** | **Zustand** | Works web + RN. |
| **Web UI kit** | **shadcn/ui + Tailwind** | Web only; mobile uses NativeWind. |
| **Agent chat UI** | **Vercel AI SDK** | Streaming + tool-call/approval rendering; points at the FastAPI streaming endpoint. |
| **Real-time** | **WebSocket** | Live quotes, fills, agent token streaming. |
| **Auth / tenancy** | FastAPI-issued **JWT** (or Clerk/Auth0) | **Multi-tenant**; per-request isolation enforced server-side. |
| **LLM provider** | **Claude** | Tool-use + reasoning quality. |

---

## 8. Repository Structure (monorepo)

Monorepo via **pnpm + Turborepo**. The split protects the future mobile path: web and mobile share framework-agnostic logic, not UI.

```
/packages
  /core      ← pure TS: API clients, types, WebSocket layer, domain logic
              (NO DOM / NO browser APIs — shared by web AND mobile)
  /web       ← Vite + React + shadcn/ui            (v1)
  /mobile    ← React Native + Expo                 (later; imports /core)
/backend     ← Python + FastAPI (quant + agent core)
```

**Architectural rules:**
- Zero financial/trading logic in any frontend. All strategy, risk, and broker logic lives in the Python backend.
- The frontend is a presentation client only.
- **Logic shared, presentation rebuilt** — mobile reuses `/core`, never web UI components.
- **No shared-UI frameworks for now** (no Tamagui/Solito). Accept separate web/native UIs to avoid early complexity; revisit only if mobile becomes the primary surface.

---

## 9. Frontend ⟷ Backend Contract

- **REST/JSON** for request/response (positions, orders, config, account).
- **WebSocket** for streaming: live quotes, fills, and agent token streaming.
- **OpenAPI**-generated typed clients consumed by `/packages/core`, so the frontend stays in sync with the backend automatically.
- Broker credentials and secrets live **only** in the backend, never sent to clients.

---

## 10. Compliance & Legal (must resolve before going live — not before building)

> ⚠️ **Open item — requires a securities lawyer before real-money launch.**

- Providing personalized, for-a-fee trade recommendations may classify the app as an **investment adviser** even though users hold their own funds (Option B does **not** automatically exempt us).
- **No performance guarantees** in any marketing or UI copy.
- Required disclaimers, risk disclosures, and ToS.
- Data/brokerage API terms compliance.
- **Build + paper-trade freely now; gate real-money execution behind legal sign-off.**

---

## 11. Suggested MVP Scope (v0.1)

1. Alpaca paper-trading connection (equities + options).
2. `Instrument` + `BrokerAdapter` + `MarketDataProvider` abstractions in place.
3. One or two equity strategies + one options-income strategy emitting explained signals.
4. Deterministic risk/sizing engine with hard guardrails.
5. Agent copilot: chat, trade proposals with rationale, approve-to-execute, daily narrative.
6. Backtest harness sharing the live code path.
7. Full audit log.

**Explicitly out of scope for v0.1:** full autonomy, non-Alpaca brokers, futures/crypto/FX (interfaces only), tax optimization depth, mobile app.

---

## 12. Open Questions

**Resolved:**
- [x] Tech stack — Python/FastAPI backend + Vite/React/TS web SPA + Expo (mobile, later). See §7.
- [x] LLM provider — **Claude**.
- [x] Tenancy — **multi-tenant SaaS from day one**.

**Still open:**
- [ ] Pricing: flat subscription vs tiered by features/usage.
- [ ] Backtest data source (vendor vs broker-provided history).
- [ ] Build vs buy for auth (FastAPI-issued JWT vs Clerk/Auth0).

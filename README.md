# MutualFund — Agentic Trading-Bot Marketplace

> 📄 Requirements: [English](./REQUIREMENTS.md) · [Español](./REQUIREMENTS.es.md)
> 🏗️ Architecture: [English](./ARCHITECTURE.md) · [Español](./ARCHITECTURE.es.md)

A SaaS **marketplace** where members design trading bots and sell their **signal streams** to a
community. It brings institutional-grade **process** — risk management, portfolio construction, and
research synthesis — to active retail traders.

- **Users** subscribe to free or paid bot signal streams.
- **Designers** (a premium role) design, publish, and monetize bots; the platform takes a
  configurable commission.
- **Admins** (with a configurable root admin) run the platform.

Users keep their own brokerage accounts; the app **reasons, proposes, and (on approval) executes**.
It is a copilot, not autopilot.

> ⚠️ **Not financial advice.** This software does not guarantee returns. Real-money trading is gated
> behind legal review. See [`REQUIREMENTS.md`](./REQUIREMENTS.md) §10 (Compliance & Legal).

## Core principle

> **The LLM reasons and communicates. Deterministic code decides the numbers.**

All quantitative decisions (risk sizing, optimization, backtests, greeks, P&L) run in deterministic,
testable engines in the Python backend. The LLM orchestrates and explains — it is never in the
numeric critical path.

## Planned architecture

```
/packages
  /core      pure TS — API clients, types, WebSocket layer, domain logic (shared web + mobile)
  /web       Vite + React + TypeScript (v1)
  /mobile    React Native + Expo (later)
/backend     Python + FastAPI — quant + agent core (single source of truth)
```

- **Backend:** Python + FastAPI — auth, brokers, strategies, risk, agent orchestration. REST + WebSocket, OpenAPI.
- **Web:** React + TypeScript SPA (Vite).
- **Mobile (later):** React Native + Expo, sharing `/core`.
- **LLM:** provider TBD. **Tenancy:** multi-tenant.
- **v1 assets:** US equities + options (asset-class-agnostic core).

## Status

Early design. See [`REQUIREMENTS.md`](./REQUIREMENTS.md) for the full project brief, locked decisions,
and open questions.

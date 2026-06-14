# Implementation Plan — Phase 1: Foundation, IAM, Market Data

> Covers the **3 most primitive modules** from [`ARCHITECTURE.md`](./ARCHITECTURE.md): **Foundation (X)**, **M1 Identity & Access**, **M2 Market Data**. Everything else depends on these. Goal: a runnable FastAPI backend with tenancy, auth, and a swappable market-data provider — fully tested.

---

## 0. Tooling decisions (backend)

These weren't locked in the requirements; recommended defaults below. Flagged items can change before we write code.

| Concern | Choice | Note |
|---------|--------|------|
| Language | **Python 3.12+** | |
| Package/venv manager | **uv** | Fast, modern; `uv` lockfile. (Poetry acceptable alternative.) |
| Web framework | **FastAPI** | Locked (§8). |
| ASGI server | **uvicorn** (dev), gunicorn+uvicorn workers (prod) | |
| DB | **PostgreSQL 16** | Multi-tenant shared DB. |
| ORM + migrations | **SQLAlchemy 2.0** (async) + **Alembic** | |
| Validation/settings | **Pydantic v2** + **pydantic-settings** | |
| Auth libs | **Authlib** (OAuth/OIDC) + **PyJWT** (our tokens) | §5.1: don't hand-roll OAuth. |
| HTTP client | **httpx** (async) | For Schwab API. |
| Testing | **pytest**, **pytest-asyncio**, **httpx** test client, **testcontainers** (Postgres) | |
| Lint/format/type | **ruff** (lint+format) + **mypy** (strict) | |
| Local infra | **docker-compose** (Postgres) | |
| CI | **GitHub Actions** | lint → type → test on PR. |

**Multi-tenancy strategy (v1):** shared database, **`tenant_id` column on every tenant-scoped table**, with automatic row filtering enforced in the repository base. (Postgres Row-Level Security is a later hardening option.)

---

## 1. Backend project layout

```
/backend
  pyproject.toml            # uv project, deps, ruff/mypy config
  alembic.ini
  docker-compose.yml        # postgres
  .env.example
  /src/mutualfund
    main.py                 # FastAPI app factory, router mounting
    config.py               # Settings (pydantic-settings)
    /foundation             # MODULE X
      ids.py                # typed IDs (UserId, TenantId, ...)
      instrument.py         # Instrument, AssetClass
      clock.py              # Clock protocol, SystemClock, FixedClock
      db.py                 # engine, session, Base
      uow.py                # UnitOfWork
      repository.py         # Repository[T] base w/ tenant scoping
      tenant.py             # TenantContext
      audit.py              # AuditLog (append-only)
    /iam                    # MODULE M1
      models.py             # User, Role, Identity, Session
      roles.py              # Role enum, permissions, RoleService
      oauth.py              # Authlib provider registry (Google first)
      tokens.py             # JWT issue/verify/refresh/revoke
      service.py            # IdentityProvider, account linking
      bootstrap.py          # root-admin from config
      router.py             # /auth endpoints
      deps.py               # FastAPI deps: current_principal, require(role)
    /marketdata             # MODULE M2
      types.py              # Quote, Bar, OptionChain, TimeFrame
      provider.py           # MarketDataProvider protocol
      catalog.py            # InstrumentCatalog
      providers/
        fake.py             # CSV/in-memory provider (dev + tests)
        schwab.py           # ThinkorSwim/Schwab adapter
      router.py             # /marketdata endpoints (read)
  /migrations               # alembic versions
  /tests
    /foundation /iam /marketdata
    conftest.py             # db fixture (testcontainers), fakes
```

---

## 2. Phase 0 — Scaffolding (prerequisite)

- [ ] `uv init` backend; add deps; `pyproject.toml` with ruff + mypy (strict) config.
- [ ] `docker-compose.yml` for Postgres; `.env.example` (DB URL, JWT secret, OAuth client id/secret, Schwab creds, `ROOT_ADMIN_EMAIL`).
- [ ] `config.py` Settings loaded from env; fail-fast on missing required vars.
- [ ] `main.py` app factory + `/healthz` endpoint.
- [ ] Alembic initialized; empty baseline migration.
- [ ] GitHub Actions: `ruff check` → `mypy` → `pytest`.
- **DoD:** `uv run uvicorn` serves `/healthz`; CI green on an empty test.

---

## 3. Phase 1 — Module X: Foundation

**Goal:** persistence, tenancy, audit, clock, and the `Instrument` model — the substrate every other module builds on.

### Tasks
- [ ] **Typed IDs** (`ids.py`): `UserId`, `TenantId`, `BotId`, etc. as `NewType`/wrapped UUIDs.
- [ ] **Instrument** (`instrument.py`): `AssetClass` enum (EQUITY, OPTION), frozen `Instrument` with `multiplier/expiry/strike/option_type/tick_size`; uses `Decimal`.
- [ ] **Clock** (`clock.py`): `Clock` Protocol, `SystemClock`, `FixedClock` (tests).
- [ ] **DB layer** (`db.py`): async engine, session factory, declarative `Base`, `tenant_id` mixin.
- [ ] **UnitOfWork** (`uow.py`): async context manager wrapping a transaction.
- [ ] **Repository base** (`repository.py`): generic CRUD that **auto-injects/filters `tenant_id`** from `TenantContext` on every query — the core tenancy guarantee.
- [ ] **TenantContext** (`tenant.py`): request-scoped (contextvar) tenant id; helper to set it from the authenticated principal.
- [ ] **AuditLog** (`audit.py`): append-only `audit_events` table (no update/delete) + `record(event_type, actor, payload)`; JSON payload.
- [ ] Alembic migration for `audit_events` + a sample tenant-scoped table (for tests).

### Tests
- [ ] Repository scopes by tenant; **cross-tenant read/write is impossible** (the critical test).
- [ ] AuditLog append works; rows are not updatable via the repo API.
- [ ] `FixedClock` injects deterministic time.

**DoD:** can persist & fetch a tenant-scoped entity; cross-tenant access blocked in tests; audit entries written; `mypy --strict` clean.

---

## 4. Phase 2 — Module M1: Identity & Access (IAM)

**Goal:** OAuth login, our own JWT/session, RBAC, multi-tenant users, root-admin bootstrap.

### Tasks
- [ ] **Models** (`models.py`): `User` (id, tenant_id, email verified, status), `Identity` (provider, provider_subject, linked user), `Session`/refresh-token store.
- [ ] **Roles** (`roles.py`): `Role` enum (USER, DESIGNER, ADMIN, ROOT_ADMIN), `Permission` set, `RoleService.roles_of()` (cumulative) + `require(permission)`.
- [ ] **OAuth** (`oauth.py`): Authlib registry, **Google provider first**, designed for multiple; `begin_login(provider)` → redirect URL, `complete_login(provider, cb)` → verified identity.
- [ ] **Tokens** (`tokens.py`): issue access (short) + refresh (long) JWTs; verify; rotate; **revoke/logout**; store refresh tokens for revocation.
- [ ] **Account linking** (`service.py`): match by **verified email** → one user across providers (defined policy; default: link if email verified).
- [ ] **Root-admin bootstrap** (`bootstrap.py`): on startup, ensure the `ROOT_ADMIN_EMAIL` from config exists and holds `ROOT_ADMIN` (idempotent).
- [ ] **Router** (`router.py`): `GET /auth/{provider}/login`, `GET /auth/{provider}/callback`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.
- [ ] **FastAPI deps** (`deps.py`): `current_principal` (decodes JWT → principal + tenant), `require_role(role)` guard; sets `TenantContext`.

### Tests
- [ ] Login via a **mocked OAuth provider** → user + identity created, JWT issued.
- [ ] JWT issue/verify/expiry/refresh/revoke (revoked refresh fails).
- [ ] RBAC: USER denied admin route; ADMIN allowed; roles cumulative (DESIGNER ⊃ USER).
- [ ] Root-admin bootstrap idempotent; second account with same verified email **links**, not duplicates.

**DoD:** end-to-end (mock provider) login → JWT → protected endpoint enforces role; root admin present from config; tenancy set from principal.

> **Note — secrets:** real Google OAuth needs a client id/secret (free, Google Cloud Console). Tests use a mock provider so M1 isn't blocked on external setup.

---

## 5. Phase 3 — Module M2: Market Data

**Goal:** a swappable `MarketDataProvider` with a dev **Fake** provider and a real **Schwab/ThinkorSwim** adapter, plus an instrument catalog.

### Tasks
- [ ] **Types** (`types.py`): `TimeFrame` enum, `Quote`, `Bar`, `OptionChain`/`OptionContract` (Decimal, tz-aware datetimes).
- [ ] **Provider protocol** (`provider.py`): `quote`, `bars`, `option_chain`, `stream` (realtime).
- [ ] **InstrumentCatalog** (`catalog.py`): persist/lookup `Instrument`s (tenant-aware where relevant; reference data may be global).
- [ ] **FakeProvider** (`providers/fake.py`): serves quotes/bars from CSV/in-memory fixtures — **unblocks all downstream work without external creds**, and is the test backbone.
- [ ] **SchwabProvider** (`providers/schwab.py`): httpx client; **Schwab OAuth** (separate app-level credential flow from user auth); token storage/refresh; rate-limit handling; map Schwab responses → our types. Cover quotes, price history (bars), option chains.
- [ ] Provider selected via **config** (`MARKETDATA_PROVIDER=fake|schwab`) — swappable per §6.
- [ ] **Router** (`router.py`): read-only `GET /marketdata/quote`, `/bars`, `/options/chain`.

### Tests
- [ ] **Provider contract test suite** run against `FakeProvider` (and re-usable for any provider).
- [ ] `SchwabProvider` against **mocked HTTP** (recorded responses) — no live calls in CI.
- [ ] InstrumentCatalog CRUD + lookup.

**DoD:** fetch quote/bars/chain through the `MarketDataProvider` interface using Fake; Schwab adapter passes the same contract tests with mocked HTTP; provider swap via config only.

> **Note — Schwab onboarding:** the Schwab Developer API (formerly TD Ameritrade) requires app registration/approval, which can take time. **Build against `FakeProvider` first**; the Schwab adapter lands behind the same interface and can be finished once credentials are approved. This keeps Phase 3 (and everything after) unblocked.

---

## 6. Sequencing & milestones

```
Phase 0 (scaffold) ──► Phase 1 (Foundation) ──► Phase 2 (IAM) ──► Phase 3 (Market Data)
                                  │                   │
                                  └── tenancy + audit ┘ used by every later module
```

- **M0 — Skeleton:** server boots, CI green.
- **M1 — Foundation done:** tenancy-isolated persistence + audit + clock, tested.
- **M2 — Auth done:** OAuth→JWT→RBAC→root admin, tested (mock provider).
- **M3 — Data done:** market data via Fake (and Schwab behind same interface).

After this phase, the next build step is **M10 Ledger + M5 Sandbox** (the trust/execution core), per the architecture build order.

---

## 7. Cross-cutting definition of done (every phase)

- `ruff` + `mypy --strict` clean; `pytest` green in CI.
- No secrets in code; everything via `config.py`/env; `.env.example` updated.
- Money/quant values use `Decimal`; datetimes tz-aware.
- New tables are tenant-scoped (or explicitly justified as global reference data).
- All cross-tenant access paths covered by a negative test.

---

## 8. Risks & flags

- [ ] **Tooling confirm:** `uv` vs Poetry; Postgres assumed — OK?
- [ ] **Schwab API access** lead time (registration/approval) — mitigated by `FakeProvider`.
- [ ] **Google OAuth credentials** needed for real login (free) — mock used until then.
- [ ] Async SQLAlchemy + Alembic adds some complexity vs sync; acceptable for WebSocket-heavy app.

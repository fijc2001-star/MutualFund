# MutualFund Backend

Python/FastAPI backend. **Phase 1** implements the three most primitive modules from
[`../ARCHITECTURE.md`](../ARCHITECTURE.md): **Foundation**, **IAM**, **Market Data**.
See [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md).

## Prerequisites

- **Python 3.12+**
- [**uv**](https://docs.astral.sh/uv/) (recommended) — `pip install uv` or the official installer
- (Optional) **Docker** for local PostgreSQL; otherwise it falls back to SQLite

## Setup

```bash
cd backend
cp .env.example .env          # edit secrets as needed
uv sync --extra dev           # create venv + install deps
```

## Run

```bash
# Option A — zero infra: uses local SQLite (default DATABASE_URL)
uv run uvicorn mutualfund.main:app --reload

# Option B — Postgres
docker compose up -d
# set DATABASE_URL=postgresql+asyncpg://mutualfund:mutualfund@localhost:5432/mutualfund in .env
uv run uvicorn mutualfund.main:app --reload
```

Then open http://localhost:8000/docs (OpenAPI) and http://localhost:8000/healthz.

## Test / lint / type-check

```bash
uv run pytest -q        # full suite runs on in-memory SQLite, no Docker needed
uv run ruff check .
uv run mypy src
```

## Migrations (Postgres)

```bash
uv run alembic revision --autogenerate -m "initial: foundation + iam"
uv run alembic upgrade head
```
In development the app calls `create_all()` on startup, so migrations aren't required to boot.

## What's implemented (Phase 1)

| Module | Highlights |
|--------|-----------|
| **Foundation** | `Instrument` model, typed IDs, `Clock`, async DB, `UnitOfWork`, tenant-scoped `TenantRepository`, append-only `AuditLog` |
| **IAM** | OAuth (Authlib, Google-first) → our JWT/session, cumulative RBAC, account linking, config-bootstrapped root admin, FastAPI auth deps |
| **Market Data** | `MarketDataProvider` interface, `FakeProvider` (dev/tests), `SchwabProvider` (ThinkorSwim/Schwab), instrument catalog |

## Notes

- **No external creds required to develop:** `MARKETDATA_PROVIDER=fake` and a mock OAuth
  flow keep everything runnable. Add Google + Schwab credentials in `.env` to go live.
- **Tenancy** is enforced in `TenantRepository` (every query scoped by `TenantContext`).
- Money/quant values use `Decimal`; datetimes are timezone-aware.

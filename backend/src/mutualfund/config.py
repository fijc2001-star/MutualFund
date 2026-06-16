"""Application settings, loaded from environment / .env (REQUIREMENTS §8)."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # App
    app_name: str = "MutualFund"
    environment: str = "development"

    # Database. Defaults to local sqlite so the app boots with zero setup;
    # production uses postgresql+asyncpg (see .env.example).
    database_url: str = "sqlite+aiosqlite:///./mutualfund.db"

    # JWT (our own session tokens)
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30

    # OAuth (Google first)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    oauth_redirect_base_url: str = "http://localhost:8000"

    # Root admin bootstrap
    root_admin_email: str | None = None
    default_tenant_id: str = "00000000000000000000000000000000"

    # Marketplace (M-D/M-E). The platform never custodies money (REQUIREMENTS): paid
    # subscriptions are recorded as accounting entries, and the platform keeps this cut of
    # designer subscription revenue (the rest is the designer's net payout).
    platform_fee_pct: Decimal = Decimal("0.20")

    # Sandbox / fill models (REQUIREMENTS §5.5.1) — conservative defaults, all tunable.
    sandbox_starting_cash: Decimal = Decimal(100_000)
    slippage_bps: Decimal = Decimal(5)
    equity_commission_per_share: Decimal = Decimal(0)
    option_commission_per_contract: Decimal = Decimal("0.65")

    # Risk & sizing (M6, REQUIREMENTS §5.6) — conservative defaults, all tunable.
    risk_sizing_fraction: Decimal = Decimal("0.10")  # FixedFractional: % of equity per entry
    risk_max_position_pct: Decimal = Decimal("0.25")  # max single-name weight
    risk_max_options_leverage: Decimal = Decimal("1.0")  # options notional / equity
    risk_daily_loss_limit_pct: Decimal = Decimal("0.05")  # halt below -5% on the day
    risk_max_drawdown_pct: Decimal = Decimal("0.20")  # halt below -20% from peak
    risk_kill_switch: bool = False  # global "stop trading" override

    # Agentic strategy (M9 "agent") — uses Claude when a key is set, a deterministic stub
    # otherwise, so the strategy registers/backtests/qualifies today and goes live with a key.
    anthropic_api_key: str | None = None
    agent_model: str = "claude-opus-4-8"

    # Market data
    marketdata_provider: str = "fake"
    schwab_client_id: str | None = None
    schwab_client_secret: str | None = None
    schwab_refresh_token: str | None = None
    schwab_api_base: str = "https://api.schwabapi.com"
    schwab_token_url: str = "https://api.schwabapi.com/v1/oauth/token"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

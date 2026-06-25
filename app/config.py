"""Central application configuration.

Settings are loaded from environment variables (and a local ``.env`` file).
The core integrations (Garmin, Anthropic) are optional so the app boots in
*demo* / *offline* mode without credentials. The remaining settings tune the
production behaviour: logging, security, resilience and backups.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- Runtime environment -------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    log_json: bool = False  # structured JSON logs (recommended in production)

    # -- Garmin --------------------------------------------------------------
    garmin_email: str = ""
    garmin_password: str = ""
    garmin_token_store: str = ".garmin_tokens"
    garmin_max_retries: int = 3
    garmin_timeout_seconds: int = 30

    # -- Anthropic / Claude --------------------------------------------------
    anthropic_api_key: str = ""
    coach_model: str = "claude-sonnet-4-6"
    planner_model: str = "claude-opus-4-8"
    ai_max_retries: int = 2
    ai_timeout_seconds: int = 60
    # When the AI call fails, fall back to the offline rule-based coach.
    ai_fallback_offline: bool = True

    # -- Application ---------------------------------------------------------
    database_url: str = "sqlite:///data/running_coach.db"
    fetch_limit: int = 50
    athlete_profile: str = "Runner amatoriale, 4-5 uscite a settimana."
    rolling_window_days: int = 14

    # -- Security / web ------------------------------------------------------
    # When set, the dashboard and API require this bearer token (or ?token=).
    # Leave empty for local/personal use behind localhost.
    api_token: str = ""
    # Comma-separated list of allowed CORS origins ("*" to allow all).
    cors_origins: str = ""
    # Trust X-Forwarded-* headers (needed behind Fly.io/Render/Cloudflare).
    forwarded_allow_ips: str = "*"

    # -- Backups (Litestream → S3/R2 compatible) -----------------------------
    # Informational flags surfaced in /api/health; the actual replication is
    # handled by Litestream via docker-entrypoint.sh when configured.
    backup_enabled: bool = False

    @property
    def garmin_enabled(self) -> bool:
        """True when real Garmin credentials are configured."""
        return bool(self.garmin_email and self.garmin_password)

    @property
    def ai_enabled(self) -> bool:
        """True when a Claude API key is configured."""
        return bool(self.anthropic_api_key)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_token)

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()

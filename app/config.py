"""Central application configuration.

Settings are loaded from environment variables (and a local ``.env`` file).
The core integrations (Garmin, Anthropic) are optional so the app boots in
*demo* / *offline* mode without credentials. The remaining settings tune the
production behaviour: logging, security, resilience and backups.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
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

    # -- Strava (OAuth 2.0 + webhooks) --------------------------------------
    # Opt-in event-driven source. When an athlete connects their Strava account,
    # Strava pushes a webhook on every new activity and we pull the details.
    # All four core values come from the Strava API application settings
    # (https://www.strava.com/settings/api). Leave empty to disable Strava;
    # the rest of the app keeps working (demo/Garmin).
    strava_client_id: str = ""
    strava_client_secret: str = ""
    # Public base URL of this deployment, e.g. "https://coach.fly.dev". Used to
    # build the OAuth redirect and the webhook callback. No trailing slash.
    strava_public_base_url: str = ""
    # Arbitrary secret echoed back during the webhook subscription handshake.
    strava_webhook_verify_token: str = "running-coach"

    # -- Anthropic / Claude --------------------------------------------------
    anthropic_api_key: str = ""
    coach_model: str = "claude-haiku-4-5-20251001"
    planner_model: str = "claude-haiku-4-5-20251001"
    # Chat model routing — set in prod: medium→sonnet, complex→opus
    chat_router_model: str = "claude-haiku-4-5-20251001"
    chat_simple_model: str = "claude-haiku-4-5-20251001"
    chat_medium_model: str = "claude-haiku-4-5-20251001"   # prod: claude-sonnet-4-6
    chat_complex_model: str = "claude-haiku-4-5-20251001"  # prod: claude-opus-4-8
    ai_max_retries: int = 2
    ai_timeout_seconds: int = 60
    # When the AI call fails, fall back to the offline rule-based coach.
    ai_fallback_offline: bool = True

    # -- Application ---------------------------------------------------------
    database_url: str = "sqlite:///data/running_coach.db"
    fetch_limit: int = 50
    athlete_profile: str = "Runner amatoriale, 4-5 uscite a settimana."
    rolling_window_days: int = 14

    # -- Weather-window optimizer (Q6) --------------------------------------
    # Off by default so the general test suite and offline runs never touch the
    # network. Turn on in production (WEATHER_ENABLED=true); open-meteo needs no
    # key. Home lat/lon override the location otherwise inferred from GPS runs.
    weather_enabled: bool = False
    home_lat: float | None = None
    home_lon: float | None = None

    # -- Security / web ------------------------------------------------------
    # When set, the dashboard and API require this bearer token (or ?token=).
    # Leave empty for local/personal use behind localhost.
    api_token: str = ""
    # Comma-separated list of allowed CORS origins ("*" to allow all).
    cors_origins: str = ""
    # Trust X-Forwarded-* headers (needed behind Fly.io/Render/Cloudflare).
    forwarded_allow_ips: str = "*"
    # Fernet key for at-rest encryption of stored secrets (A10). Set
    # DATA_ENCRYPTION_KEY in production; when empty, a key is generated at
    # first use and persisted to `data_encryption_key_file` (with a warning).
    # The file lives next to the SQLite DB — on Fly that's the volume, which
    # Litestream does NOT replicate, so a leaked DB backup stays unreadable.
    data_encryption_key: str = ""
    data_encryption_key_file: str = "data/.encryption_key"
    # In-process rate limiting (A10): requests/min per client IP on /api/*,
    # with a stricter bucket on the Strava webhook. Disabled in tests.
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    rate_limit_strava_per_minute: int = 30

    # -- Raw activity object storage (Tigris / S3-compatible) ---------------
    # Used to archive every raw Garmin payload (summary JSON, details streams,
    # splits, weather, gear, GPX, FIT/ORIGINAL, TCX) for every activity, not
    # only running ones. Leave empty to disable raw archival; the rest of the
    # app continues to work.
    #
    # On Fly.io with Tigris ("fly storage create") the platform injects
    # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, AWS_ENDPOINT_URL_S3
    # and BUCKET_NAME as secrets. The settings below accept S3_*-prefixed
    # variables, falling back to those Tigris defaults via env aliases.
    s3_endpoint_url: str = Field(
        default="",
        validation_alias=AliasChoices("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3"),
    )
    s3_region: str = Field(
        default="auto",
        validation_alias=AliasChoices("S3_REGION", "AWS_REGION"),
    )
    s3_access_key_id: str = Field(
        default="",
        validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    )
    s3_secret_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    s3_bucket: str = Field(
        default="",
        validation_alias=AliasChoices("S3_BUCKET", "BUCKET_NAME"),
    )
    s3_key_prefix: str = "garmin"
    # When true, ingest_runs also archives raw payloads to object storage for
    # every Garmin activity (running and non-running). Auto-on when an S3
    # endpoint and bucket are configured; can be force-disabled for tests.
    raw_archive_enabled: bool = True

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
    def strava_enabled(self) -> bool:
        """True when Strava OAuth credentials are configured."""
        return bool(self.strava_client_id and self.strava_client_secret)

    @property
    def strava_redirect_uri(self) -> str:
        """OAuth callback URL derived from the public base URL."""
        base = self.strava_public_base_url.rstrip("/")
        return f"{base}/api/strava/callback" if base else ""

    @property
    def strava_webhook_callback_url(self) -> str:
        """Webhook callback URL derived from the public base URL."""
        base = self.strava_public_base_url.rstrip("/")
        return f"{base}/api/strava/webhook" if base else ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def s3_enabled(self) -> bool:
        """True when an S3-compatible bucket is fully configured."""
        return bool(
            self.s3_endpoint_url
            and self.s3_bucket
            and self.s3_access_key_id
            and self.s3_secret_access_key
        )

    @property
    def raw_archive_active(self) -> bool:
        """True when raw archival should run during ingest."""
        return self.raw_archive_enabled and self.s3_enabled

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

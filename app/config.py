"""Central application configuration.

Settings are loaded from environment variables (and a local ``.env`` file).
Everything is optional so the app can boot in *demo* / *offline* mode without
any external credentials — useful for development, CI and first-run UX.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Garmin
    garmin_email: str = ""
    garmin_password: str = ""
    garmin_token_store: str = ".garmin_tokens"

    # Anthropic / Claude
    anthropic_api_key: str = ""
    coach_model: str = "claude-sonnet-4-6"
    planner_model: str = "claude-opus-4-8"

    # Application
    database_url: str = "sqlite:///data/running_coach.db"
    fetch_limit: int = 10
    athlete_profile: str = "Runner amatoriale, 4-5 uscite a settimana."
    rolling_window_days: int = 14

    @property
    def garmin_enabled(self) -> bool:
        """True when real Garmin credentials are configured."""
        return bool(self.garmin_email and self.garmin_password)

    @property
    def ai_enabled(self) -> bool:
        """True when a Claude API key is configured."""
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()

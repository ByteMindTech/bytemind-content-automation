"""Application configuration — Pydantic v2 BaseSettings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    log_level: str = "INFO"

    # ── Security ─────────────────────────────────────────────
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    actions_api_key: str = Field(..., min_length=32)

    # ── Database ─────────────────────────────────────────────
    database_url: str = Field(...)
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── AI Providers ─────────────────────────────────────────
    gemini_api_key: str = Field(default="")
    gemini_model: str = "gemini-1.5-pro"
    gemini_max_tokens: int = 8192
    gemini_temperature: float = 0.7

    openai_api_key: str = Field(default="")
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096

    ai_provider: Literal["gemini", "openai", "auto"] = "auto"

    # ── Medium ───────────────────────────────────────────────
    medium_integration_token: str = Field(default="")
    medium_author_id: str = Field(default="")
    medium_dry_run: bool = True
    medium_default_status: Literal["draft", "public", "unlisted"] = "draft"
    medium_canonical_base_url: str = "https://bytemind.fr/blogs"

    # ── Content ──────────────────────────────────────────────
    content_source_path: str = "../ByteMindTech/src/content/blog"
    content_watch_extensions: str = ".md"

    # ── Scheduling ───────────────────────────────────────────
    scheduler_timezone: str = "Europe/Paris"
    scheduler_publish_cron: str = "0 10 * * 5"

    # ── Rate Limiting ────────────────────────────────────────
    rate_limit_generate: str = "10/minute"
    rate_limit_publish: str = "5/minute"
    rate_limit_global: str = "100/minute"

    # ── CORS ────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    @field_validator("gemini_temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("gemini_temperature must be between 0.0 and 2.0")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Call once per process."""
    return Settings()

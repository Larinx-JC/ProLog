"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, sourced from the environment.

    A single source of truth for config keeps every layer (DB session,
    CORS, auth) reading the same validated values instead of re-parsing
    os.environ independently in multiple places.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "mysql+pymysql://prolog:prolog@localhost:3306/prolog"
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: str | list[str]) -> list[str] | str:
        """Allow CORS_ORIGINS to be given as a comma-separated string in .env."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, constructed once and cached.

    lru_cache gives a singleton without a mutable global; tests can still
    get a fresh read by calling get_settings.cache_clear() first.
    """
    return Settings()

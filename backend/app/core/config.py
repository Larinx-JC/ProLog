"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, sourced from the environment.

    A single source of truth for config keeps every layer (DB session,
    CORS, auth) reading the same validated values instead of re-parsing
    os.environ independently in multiple places.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str = "change-me"
    database_url: str = "mysql+pymysql://prolog:prolog@localhost:3306/prolog"
    # NoDecode stops pydantic-settings from JSON-decoding the raw env string
    # before our validator runs (list fields are auto-JSON-decoded by
    # default, so a plain comma-separated value would fail with a
    # SettingsError before _split_csv ever saw it).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    public_url: str = "http://localhost:5173"
    secure_cookies: bool = False
    session_idle_seconds: int = Field(default=1800, ge=1, le=86400)
    session_max_seconds: int = Field(default=43200, ge=1, le=604800)
    activation_seconds: int = Field(default=86400, ge=1, le=604800)
    recovery_seconds: int = Field(default=1800, ge=1, le=86400)
    auth_window_seconds: int = Field(default=900, ge=1, le=86400)
    login_account_limit: int = Field(default=5, ge=1, le=1000)
    login_address_limit: int = Field(default=30, ge=1, le=10000)
    grant_address_limit: int = Field(default=20, ge=1, le=10000)

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        """Reject inconsistent durations, unsafe origins, and production defaults."""
        if self.session_idle_seconds > self.session_max_seconds:
            raise ValueError("Session idle timeout cannot exceed its absolute maximum.")
        for origin in [self.public_url, *self.cors_origins]:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("Public URL and CORS origins must be HTTP(S) origins.")
            if self.app_env == "production" and parsed.scheme != "https":
                raise ValueError("Production authentication requires HTTPS origins.")
        if self.app_env == "production":
            if (
                not self.secure_cookies
                or len(self.secret_key) < 32
                or "change-me" in self.secret_key
            ):
                raise ValueError(
                    "Production requires Secure cookies and a strong 32+ character secret."
                )
        self.public_url = self.public_url.rstrip("/")
        self.cors_origins = [origin.rstrip("/") for origin in self.cors_origins]
        return self

    @property
    def session_cookie(self) -> str:
        """Select the host-only cookie prefix required by the production policy."""
        return "__Host-prolog_session" if self.secure_cookies else "prolog_session"

    @property
    def csrf_cookie(self) -> str:
        """Name the separate pre-authentication cookie used to protect login."""
        return "__Host-prolog_csrf" if self.secure_cookies else "prolog_csrf"

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


def escape_for_configparser(value: str) -> str:
    """Double every "%" so a configparser-backed tool (Alembic's alembic.ini)
    doesn't treat it as interpolation syntax.

    A percent-encoded URL component — e.g. a password containing "%40" for
    "@" — otherwise raises ValueError the next time the value is read back
    via configparser's .get()/.get_section().
    """
    return value.replace("%", "%%")

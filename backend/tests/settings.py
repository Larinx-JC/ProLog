"""Shared settings configuration for tests that must ignore local dotenv files."""

from pydantic_settings import SettingsConfigDict

from app.core.config import Settings


class SettingsWithoutDotenv(Settings):
    """Retain production validation and environment loading, but skip local .env files.

    Class configuration avoids the runtime-only _env_file constructor option
    that Pyright/Pylance omits from its generated Pydantic model signature.
    Pydantic merges this with the inherited Settings configuration.
    """

    model_config = SettingsConfigDict(env_file=None)

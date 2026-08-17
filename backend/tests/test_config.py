"""Unit tests for app.core.config."""

from app.core.config import Settings, get_settings


def test_get_settings_is_cached() -> None:
    """get_settings() must return the same instance across calls (singleton)."""
    assert get_settings() is get_settings()


def test_cors_origins_parsed_from_csv_string() -> None:
    """CORS_ORIGINS given as 'a, b' should split into a trimmed list."""
    settings = Settings(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_accepts_list_directly() -> None:
    """Constructing with an actual list should pass through unchanged."""
    settings = Settings(cors_origins=["http://a.test"])
    assert settings.cors_origins == ["http://a.test"]

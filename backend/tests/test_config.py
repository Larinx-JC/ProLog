"""Unit tests for app.core.config."""

import pytest

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


def test_cors_origins_parsed_from_real_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-origin CORS_ORIGINS set as an actual env var must not raise.

    list[str] fields are JSON-decoded by pydantic-settings before any field
    validator runs, so a plain (non-JSON) value like `http://localhost:5173`
    would raise SettingsError without the NoDecode marker on the field.
    This exercises the real env-loading path, not just direct construction.
    """
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    settings = Settings()
    assert settings.cors_origins == ["http://localhost:5173"]


def test_cors_origins_csv_parsed_from_real_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comma-separated CORS_ORIGINS set as an actual env var should split."""
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    settings = Settings()
    assert settings.cors_origins == ["http://a.test", "http://b.test"]

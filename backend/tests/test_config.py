"""Unit tests for app.core.config."""

from configparser import ConfigParser

import pytest

from app.core.config import Settings, escape_for_configparser, get_settings


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


def test_escape_for_configparser_survives_percent_encoded_password() -> None:
    """A DATABASE_URL with a percent-encoded password (e.g. '%40' for '@')
    must round-trip unchanged through a real configparser set/get cycle.

    Alembic stores sqlalchemy.url via configparser, whose BasicInterpolation
    treats a lone "%" as the start of a %(name)s reference and raises
    ValueError unless it's escaped to "%%" first — this is what Alembic's
    env.py relies on escape_for_configparser() to do.
    """
    raw_url = "mysql+pymysql://user:p%40ss@localhost/db"

    parser = ConfigParser()
    parser.add_section("alembic")
    parser.set("alembic", "sqlalchemy.url", escape_for_configparser(raw_url))

    assert parser.get("alembic", "sqlalchemy.url") == raw_url


def test_escape_for_configparser_leaves_plain_url_unchanged() -> None:
    """A URL with no "%" should pass through both the escape and a
    configparser round-trip unchanged."""
    raw_url = "mysql+pymysql://prolog:prolog@localhost:3306/prolog"

    parser = ConfigParser()
    parser.add_section("alembic")
    parser.set("alembic", "sqlalchemy.url", escape_for_configparser(raw_url))

    assert parser.get("alembic", "sqlalchemy.url") == raw_url

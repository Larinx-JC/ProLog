"""Regression for editor-compatible dotenv isolation in test configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.settings import SettingsWithoutDotenv


def test_test_settings_ignore_dotenv_but_read_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignore a broken local file while retaining real environment parsing and validation."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SESSION_IDLE_SECONDS", raising=False)
    (tmp_path / ".env").write_text("SESSION_IDLE_SECONDS=invalid\n", encoding="utf-8")

    # The normal application's dotenv configuration must remain unchanged.
    with pytest.raises(ValidationError, match="session_idle_seconds"):
        Settings(app_env="test")
    assert Settings.model_config.get("env_file") == ".env"
    assert SettingsWithoutDotenv(app_env="test").session_idle_seconds == 1800
    assert SettingsWithoutDotenv.model_config.get("env_file_encoding") == "utf-8"

    monkeypatch.setenv("SESSION_IDLE_SECONDS", "120")
    assert SettingsWithoutDotenv(app_env="test").session_idle_seconds == 120
    monkeypatch.setenv("SESSION_IDLE_SECONDS", "0")
    with pytest.raises(ValidationError, match="session_idle_seconds"):
        SettingsWithoutDotenv(app_env="test")

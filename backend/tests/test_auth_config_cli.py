"""Configuration and trusted-console acceptance tests."""

import pytest
from pydantic import ValidationError

from app.cli import main
from app.core.config import Settings
from app.services.auth import AuthService
from tests.auth_fixtures import PASSWORD, REPLACEMENT


@pytest.mark.parametrize(
    "values",
    [
        {"session_idle_seconds": 0},
        {"session_max_seconds": -1},
        {"session_idle_seconds": 100, "session_max_seconds": 50},
        {"activation_seconds": 0},
        {"recovery_seconds": 0},
        {"public_url": "https://user:password@factory.test"},
        {"cors_origins": ["*"]},
        {"public_url": "https://factory.test/path"},
    ],
)
def test_invalid_auth_configuration(values: dict) -> None:
    """Reject invalid ranges/origins during configuration loading."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_production_requires_secure_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate real environment loading, including production secrets and HTTPS."""
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("PUBLIC_URL", "https://factory.test")
    monkeypatch.setenv("CORS_ORIGINS", "https://factory.test")
    monkeypatch.setenv("SECURE_COOKIES", "true")
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-with-more-than-32-characters")
    assert Settings(_env_file=None).session_cookie == "__Host-prolog_session"


def test_cli_bootstrap_repetition_recovery_and_password_confirmation(
    auth: AuthService, capsys: pytest.CaptureFixture
) -> None:
    """The CLI prompts, refuses duplicate bootstrap, and supports audited local recovery."""
    args = ["bootstrap-admin", "--account", "admin.test", "--name", "Admin"]
    assert main(args, auth, lambda _: PASSWORD) == 0
    assert main(args, auth, lambda _: PASSWORD) == 1
    assert main(["recover-admin", "--account", "admin.test"], auth, lambda _: REPLACEMENT) == 0
    answers = iter([PASSWORD, REPLACEMENT])
    assert main(args, auth, lambda _: next(answers)) == 1
    assert PASSWORD not in capsys.readouterr().out


def test_cli_rejects_password_in_process_arguments(
    auth: AuthService, capsys: pytest.CaptureFixture
) -> None:
    """Credentials cannot be supplied through a visible --password argument."""
    with pytest.raises(SystemExit) as error:
        main(["bootstrap-admin", "--account", "admin.test", "--password", PASSWORD], auth)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err


def test_cli_invalid_password_leaves_no_partial_bootstrap(auth: AuthService) -> None:
    """A rejected short password rolls back the new account and bootstrap marker."""
    args = ["bootstrap-admin", "--account", "admin.test"]
    assert main(args, auth, lambda _: "too-short") == 1
    assert main(args, auth, lambda _: PASSWORD) == 0

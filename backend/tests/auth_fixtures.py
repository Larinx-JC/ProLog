"""Shared synthetic accounts and controlled time for authentication tests."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.time import Clock
from app.services.auth import AuthService
from app.services.auth_types import GrantIssued, SessionIssued

PASSWORD = "A correct factory passphrase!"
REPLACEMENT = "A different factory passphrase!"


@dataclass
class FrozenClock(Clock):
    """Move time explicitly; tests never need to sleep for expiry."""

    value: datetime = datetime(2026, 9, 7, 12, 0, 0)

    def now(self) -> datetime:
        """Return the controlled UTC-naive instant."""
        return self.value

    def advance(self, seconds: float) -> None:
        """Move only this test's clock by a deterministic interval."""
        self.value += timedelta(seconds=seconds)


def bootstrap_login(auth: AuthService, account: str = "admin.test") -> SessionIssued:
    """Create a synthetic initial Admin and log in through the actual service."""
    auth.bootstrap(account, "管理员", PASSWORD)
    return auth.login(account, PASSWORD, "bootstrap-client")


def invite_login(
    auth: AuthService, admin: SessionIssued, role: str = "operator", account: str = "operator.test"
) -> tuple[GrantIssued, SessionIssued]:
    """Exercise invitation and activation before obtaining a non-Admin session."""
    grant = auth.invite(admin.token, account, "操作员", role)
    auth.consume_grant(grant.token, "activation", PASSWORD, "activation-client")
    return grant, auth.login(account, PASSWORD, account)

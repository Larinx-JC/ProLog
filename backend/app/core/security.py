"""Password and opaque-token primitives shared by authentication services."""

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


class Passwords:
    """Bound password inputs and hash them with explicit Argon2id parameters."""

    def __init__(self) -> None:
        """Pin parameters so dependency upgrades do not silently change policy."""
        self.hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        """Hash an accepted password without trimming or normalizing its content."""
        if not 15 <= len(password) <= 128:
            raise ValueError("Password must contain 15 to 128 characters.")
        return self.hasher.hash(password)

    def verify(self, password: str, encoded: str | None) -> bool:
        """Use a dummy hash for unknown accounts and reject invalid legacy hashes."""
        if len(password) > 128:
            return False
        try:
            valid = self.hasher.verify(encoded or self.dummy_hash, password)
            return valid and encoded is not None
        except VerifyMismatchError:
            return False
        except (VerificationError, InvalidHashError):
            # Pending/invalid legacy hashes should not make an account cheaper
            # to probe than an unknown account with a dummy Argon2 verification.
            try:
                self.hasher.verify(self.dummy_hash, password)
            except (VerificationError, InvalidHashError):
                pass
            return False

    def needs_rehash(self, encoded: str) -> bool:
        """Identify old Argon2 parameters after successful credential verification."""
        return self.hasher.check_needs_rehash(encoded)


class Tokens:
    """Generate opaque credentials and derive domain-separated CSRF/counter values."""

    def __init__(self, secret: str) -> None:
        """Keep the configured server secret out of representations and responses."""
        self._secret = secret.encode("utf-8")

    def issue(self) -> str:
        """Return a URL-safe token containing 256 random bits."""
        return secrets.token_urlsafe(32)

    def digest(self, token: str) -> str:
        """Store only a SHA-256 digest of an unpredictable opaque token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def keyed_digest(self, purpose: str, value: str) -> str:
        """Separate CSRF and rate-limit key domains using a server-keyed digest."""
        return hmac.new(self._secret, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

    def csrf_valid(self, cookie: str, submitted: str) -> bool:
        """Compare a cookie-bound CSRF proof without a timing-sensitive equality."""
        return (
            bool(cookie)
            and re.fullmatch(r"[0-9a-f]{64}", submitted) is not None
            and hmac.compare_digest(self.keyed_digest("csrf", cookie), submitted)
        )


def normalize_account(value: str) -> str:
    """Use one canonical account identifier for login, uniqueness, and rate limits."""
    account = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,99}", account):
        raise ValueError(
            "Account must be 3–100 ASCII letters, digits, dots, underscores or hyphens."
        )
    return account

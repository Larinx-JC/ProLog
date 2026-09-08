"""Observable rejection and representation tests for password/token primitives."""

import pytest

from app.core.security import Passwords, Tokens, normalize_account
from tests.auth_fixtures import PASSWORD


def test_password_hash_is_salted_and_rejects_bad_or_unknown_credentials(
    passwords: Passwords,
) -> None:
    """Equal passwords have distinct hashes; only the exact password verifies."""
    first, second = passwords.hash(PASSWORD), passwords.hash(PASSWORD)
    assert first != second and first.startswith("$argon2id$")
    assert passwords.verify(PASSWORD, first)
    assert not passwords.needs_rehash(first)
    for password, encoded in [
        ("wrong", first),
        (PASSWORD, None),
        (PASSWORD, "broken"),
        ("x" * 129, first),
    ]:
        assert not passwords.verify(password, encoded)


@pytest.mark.parametrize("password", ["x" * 14, "x" * 129])
def test_password_length_rejected(passwords: Passwords, password: str) -> None:
    """Reject passwords outside the documented length limits before hashing."""
    with pytest.raises(ValueError):
        passwords.hash(password)


def test_unicode_spaces_and_password_boundaries(passwords: Passwords) -> None:
    """Accept long passphrases without trimming or losing Unicode characters."""
    for password in ["x" * 15, "x" * 128, " 中文工厂口令 testing passphrase "]:
        assert passwords.verify(password, passwords.hash(password))


def test_token_and_csrf_domains() -> None:
    """Tokens differ, digests hide raw values, and malformed CSRF proofs reject."""
    tokens = Tokens("testing")
    first, second = tokens.issue(), tokens.issue()
    assert first != second and len(first) == 43
    assert len(tokens.digest(first)) == 64 and first not in tokens.digest(first)
    csrf = tokens.keyed_digest("csrf", first)
    assert tokens.csrf_valid(first, csrf)
    assert csrf != tokens.keyed_digest("rate", first)
    for cookie, proof in [(second, csrf), ("", csrf), (first, "wrong"), (first, "非ASCII")]:
        assert not tokens.csrf_valid(cookie, proof)


@pytest.mark.parametrize("invalid", ["aa", "has space", "a@b", "管理员", "x" * 101, "_start"])
def test_invalid_account_identifiers(invalid: str) -> None:
    """Reject ambiguous or unsupported login identifiers consistently."""
    with pytest.raises(ValueError):
        normalize_account(invalid)


def test_account_canonicalization() -> None:
    """One normalized identity underlies login and uniqueness checks."""
    assert normalize_account("  Admin.TEST-1_2 ") == "admin.test-1_2"

"""Safe authentication results and the shared authorization vocabulary."""

from dataclasses import dataclass, field
from enum import StrEnum

from app.models import User


class AuthError(Exception):
    """An expected rejection with an explicit safe-to-commit failure marker."""

    def __init__(self, code: str, status: int = 400, persist_failure: bool = False) -> None:
        """Expose only a stable public code, never credentials or database details."""
        super().__init__(code)
        self.code = code
        self.status = status
        self.persist_failure = persist_failure


class Permission(StrEnum):
    """Operation capabilities reused by current auth and later production APIs."""

    RUN_READ = "run:read"
    RUN_CREATE = "run:create"
    RUN_EDIT_OWN = "run:edit_own"
    RUN_EDIT_ALL = "run:edit_all"
    RUN_REVIEW = "run:review"
    MATERIAL_READ = "material:read"
    MATERIAL_MANAGE = "material:manage"
    AUDIT_READ = "audit:read"
    EXPORT = "export:create"
    USER_MANAGE = "user:manage"
    PRODUCTION_SETTINGS_MANAGE = "production_settings:manage"


ROLE_PERMISSIONS = {
    "admin": frozenset(Permission),
    "operator": frozenset(
        {
            Permission.RUN_READ,
            Permission.RUN_CREATE,
            Permission.RUN_EDIT_OWN,
            Permission.MATERIAL_READ,
        }
    ),
    "reviewer": frozenset(
        {Permission.RUN_READ, Permission.MATERIAL_READ, Permission.AUDIT_READ, Permission.EXPORT}
    ),
}


@dataclass(frozen=True)
class Identity:
    """Detached public user data with no hashes, grants, or session secrets."""

    id: int
    name: str
    account: str
    position: str | None
    role: str
    is_active: bool
    must_change_password: bool
    activated: bool

    @classmethod
    def from_user(cls, user: User) -> "Identity":
        """Read only explicitly approved fields while the database session is open."""
        return cls(
            user.id,
            user.name,
            user.account,
            user.position,
            user.role.code,
            user.is_active,
            user.must_change_password,
            user.activated_at is not None,
        )

    def require(self, permission: Permission) -> None:
        """Fail closed for unknown roles, disabled/pending users, and forced changes."""
        if (
            not self.is_active
            or not self.activated
            or self.must_change_password
            or permission not in ROLE_PERMISSIONS.get(self.role, frozenset())
        ):
            raise AuthError("permission_denied", 403)

    def can_edit_run(self, created_by_id: int) -> bool:
        """Enforce ownership; Section 4 separately enforces lifecycle edit eligibility."""
        try:
            self.require(
                Permission.RUN_EDIT_ALL if self.role == "admin" else Permission.RUN_EDIT_OWN
            )
        except AuthError:
            return False
        return self.role == "admin" or self.id == created_by_id


@dataclass(frozen=True)
class SessionIssued:
    """A one-time transport result; repr excludes the raw session credential."""

    user: Identity
    token: str = field(repr=False)


@dataclass(frozen=True)
class GrantIssued:
    """An Admin-delivered link shown once, with sensitive fields excluded from repr."""

    user: Identity
    purpose: str
    url: str = field(repr=False)
    token: str = field(repr=False)

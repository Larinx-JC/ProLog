"""Transaction, audit, and throttle plumbing shared by authentication services."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Tokens
from app.models import AuditLog, AuthState, AuthThrottle, User
from app.services.auth_types import AuthError


@contextmanager
def auth_transaction(factory: Callable[[], Session]) -> Iterator[Session]:
    """Serialize auth changes in MySQL and commit only explicitly safe failures."""
    with factory() as db:
        try:
            state = db.scalar(select(AuthState).where(AuthState.id == 1).with_for_update())
            if state is None:
                raise AuthError("authentication_unavailable", 503)
            yield db
        except AuthError as error:
            if error.persist_failure:
                db.commit()
            else:
                db.rollback()
            raise
        except BaseException:
            db.rollback()
            raise
        else:
            db.commit()


def audit(
    db: Session,
    now: datetime,
    action: str,
    actor: User | None = None,
    target: User | None = None,
    before: str | None = None,
    after: str | None = None,
    reason: str | None = None,
) -> None:
    """Stage a credential-free audit row inside the caller's transaction."""
    db.add(
        AuditLog(
            occurred_at=now,
            action=action,
            actor_id=actor.id if actor else None,
            target_type="user" if target else "authentication",
            target_id=target.id if target else None,
            target_label=target.account if target else "authentication",
            before_value=before,
            after_value=after,
            reason=reason,
        )
    )


class RateLimiter:
    """Database counters protected by the shared authentication transaction lock."""

    def __init__(self, settings: Settings, tokens: Tokens) -> None:
        """Reuse validated settings and a keyed digest for counter identifiers."""
        self.settings = settings
        self.tokens = tokens

    def consume(self, db: Session, now: datetime, scopes: list[tuple[str, str, int]]) -> None:
        """Consume one attempt per scope; a rejected request cannot reset a window."""
        db.execute(delete(AuthThrottle).where(AuthThrottle.expires_at <= now))
        rows = []
        for purpose, value, limit in scopes:
            key = self.tokens.keyed_digest(f"rate:{purpose}", value)
            row = db.get(AuthThrottle, key)
            if row is not None and row.attempts >= limit:
                raise AuthError("too_many_attempts", 429, persist_failure=True)
            rows.append((key, row))
        for key, row in rows:
            if row is None:
                db.add(
                    AuthThrottle(
                        key=key,
                        attempts=1,
                        expires_at=now + timedelta(seconds=self.settings.auth_window_seconds),
                    )
                )
            else:
                row.attempts += 1
        db.flush()

    def clear_account(self, db: Session, account: str) -> None:
        """Reset failed account attempts after successful authentication/recovery."""
        db.execute(
            delete(AuthThrottle).where(
                AuthThrottle.key == self.tokens.keyed_digest("rate:account", account)
            )
        )

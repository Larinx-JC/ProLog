"""Audited Admin display preferences shared by every current and historical screen."""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.numeric import AccuracyPolicy
from app.models import User
from app.services.auth_store import auth_transaction
from app.services.auth_types import Identity, Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    check_revision,
    json_text,
    require_text,
)


class DisplaySettingsService(ProductionStore):
    """Change current presentation without rewriting material, measurement or run data."""

    def get(self, token: str) -> Document:
        """Expose current formatting to every permitted reader without extending idle time."""
        with auth_transaction(self.auth.factory) as db:
            actor, _ = self.auth.sessions.require(db, token, self.auth.clock.now())
            Identity.from_user(actor).require(Permission.RUN_READ)
            return Document(json_text(self.display_document(db)))

    def update(
        self,
        token: str,
        request_id: str,
        expected_revision: int,
        precision: AccuracyPolicy,
        reason: str,
    ) -> Document:
        """Apply Admin display choices globally with an audited revision and durable retry."""
        payload = dict(
            expected_revision=expected_revision, precision=asdict(precision), reason=reason
        )

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Persist display preferences independently of recording-policy compatibility."""
            row = self.display_settings(db)
            check_revision(row, expected_revision)
            explanation = require_text(reason, 4000)
            before = self.display_document(db)
            for name, value in asdict(precision).items():
                setattr(row, name, value)
            row.revision += 1
            row.updated_at, row.updated_by_id = now, actor.id
            after = self.display_document(db)
            self.audit(
                db,
                actor,
                now,
                "display_settings_changed",
                "display_settings",
                1,
                "Factory display settings",
                before,
                after,
                explanation,
            )
            return after

        return self.write(
            token,
            "display.update",
            request_id,
            payload,
            Permission.PRODUCTION_SETTINGS_MANAGE,
            mutate,
        )

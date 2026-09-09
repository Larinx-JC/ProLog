"""Admin-managed factory accuracy and current operational authority."""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.measurements import Rules
from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import AccuracyVersion, Material, User
from app.services.auth_store import auth_transaction
from app.services.auth_types import Identity, Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    check_revision,
    json_text,
    policy_from,
    require_text,
    snapshot,
)


class AccuracySettingsService(ProductionStore):
    """Create immutable policies; permission switches take effect on subsequent writes."""

    def get(self, token: str) -> Document:
        """Return settings to Admin without renewing idle time during background reads."""
        with auth_transaction(self.auth.factory) as db:
            actor, _ = self.auth.sessions.require(db, token, self.auth.clock.now())
            Identity.from_user(actor).require(Permission.PRODUCTION_SETTINGS_MANAGE)
            return Document(json_text(self._document(db)))

    def _document(self, db: Session) -> dict:
        """Assemble current policy and operational permission without mutable ORM exposure."""
        settings = self.settings(db)
        return dict(
            id=1,
            revision=settings.revision,
            accuracy_version_id=settings.accuracy_version_id,
            operator_abnormal_allowed=settings.operator_abnormal_allowed,
            accuracy=asdict(policy_from(self.policy(db, settings.accuracy_version_id))),
        )

    def update(
        self,
        token: str,
        request_id: str,
        expected_revision: int,
        accuracy: AccuracyPolicy,
        operator_abnormal_allowed: bool,
        reason: str,
    ) -> Document:
        """Audit a new factory policy without altering runs or rounding material standards."""
        payload = dict(
            expected_revision=expected_revision,
            accuracy=asdict(accuracy),
            operator_abnormal_allowed=operator_abnormal_allowed,
            reason=reason,
        )

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Validate current standards and publish the new version atomically."""
            settings = self.settings(db)
            check_revision(settings, expected_revision)
            explanation = require_text(reason, 4000)
            if type(operator_abnormal_allowed) is not bool:
                raise DomainError("invalid_permission_switch")
            # Inactive materials are validated on reactivation, avoiding an obsolete
            # archived standard preventing a factory-wide precision change forever.
            for material in db.scalars(select(Material).where(Material.is_active.is_(True))):
                try:
                    Rules(**snapshot(material, Rules)).validate(accuracy)
                except DomainError as error:
                    raise DomainError("material_precision_conflict", 409) from error
            before = self._document(db)
            version = AccuracyVersion(
                **asdict(accuracy),
                calculation_version="target_v1",
                created_at=now,
                created_by_id=actor.id,
            )
            db.add(version)
            db.flush()
            settings.accuracy_version_id = version.id
            settings.operator_abnormal_allowed = operator_abnormal_allowed
            settings.revision += 1
            after = self._document(db)
            self.audit(
                db,
                actor,
                now,
                "production_settings_changed",
                "production_settings",
                1,
                "Factory production settings",
                before,
                after,
                explanation,
            )
            return after

        return self.write(
            token,
            "settings.update",
            request_id,
            payload,
            Permission.PRODUCTION_SETTINGS_MANAGE,
            mutate,
        )

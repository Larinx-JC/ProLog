"""Terminal Admin review, including explicit self-review and incomplete-data evidence."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.numeric import DomainError
from app.models import AuditLog, Measurement, ReviewResolution, Run, RunStatus, User
from app.services.auth_types import Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    check_revision,
    require_text,
    stamp_update,
)


class ReviewService(ProductionStore):
    """Record a consistent final decision; reviewed runs cannot be reopened or edited."""

    def review(
        self,
        token: str,
        request_id: str,
        identifier: int,
        expected_revision: int,
        resolution: str,
        reason: str,
    ) -> Document:
        """Require Admin, source-appropriate resolution and reason for every review."""

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Preserve closure exceptions and explicitly audit review of the actor's own work."""
            run = db.get(Run, identifier)
            if run is None:
                raise DomainError("run_not_found", 404)
            check_revision(run, expected_revision)
            if run.status != RunStatus.PENDING_REVIEW:
                raise DomainError("run_not_pending_review", 409)
            if (
                run.end_time is None
                or run.end_time > now
                or run.end_time < run.start_time
                or run.pending_from not in {RunStatus.ACTIVE, RunStatus.ABNORMAL}
                or run.reviewed_by_id is not None
                or run.reviewed_at is not None
                or run.review_resolution is not None
                or run.review_reason is not None
                or run.missing_count_at_close is None
                or run.missing_count_at_close < 0
                or (run.missing_count_at_close > 0 and not run.closure_exception_reason)
            ):
                raise DomainError("inconsistent_review_state", 409)
            try:
                decision = ReviewResolution(resolution)
            except ValueError as error:
                raise DomainError("invalid_review_resolution") from error
            permitted = (
                {ReviewResolution.APPROVED}
                if run.pending_from == RunStatus.ACTIVE
                else {ReviewResolution.CONFIRMED_ABNORMAL, ReviewResolution.FALSE_ALARM}
            )
            if decision not in permitted:
                raise DomainError("invalid_review_resolution")
            explanation = require_text(reason, 4000)
            before = self.run_document(db, run)
            authored_measurement = (
                db.scalar(
                    select(AuditLog.id)
                    .where(
                        AuditLog.actor_id == actor.id,
                        AuditLog.target_type == "measurement",
                        AuditLog.action.in_(["measurement_recorded", "measurement_corrected"]),
                        AuditLog.target_id.in_(
                            select(Measurement.id).where(Measurement.run_id == run.id)
                        ),
                    )
                    .limit(1)
                )
                is not None
            )
            self_review = actor.id == run.created_by_id or authored_measurement
            run.status, run.review_resolution = RunStatus.REVIEWED, decision
            run.review_reason, run.reviewed_by_id = explanation, actor.id
            run.reviewed_at = now
            stamp_update(run, now)
            run.revision += 1
            after = self.run_document(db, run)
            after["self_review"] = self_review
            self.audit(
                db,
                actor,
                now,
                "run_reviewed",
                "run",
                run.id,
                run.run_code,
                before,
                after,
                explanation,
            )
            return after

        return self.write(
            token,
            "run.review",
            request_id,
            dict(
                id=identifier,
                expected_revision=expected_revision,
                resolution=resolution,
                reason=reason,
            ),
            Permission.RUN_REVIEW,
            mutate,
        )

"""Run creation, immutable snapshots and explicit closure with missing-data exceptions."""

from dataclasses import asdict
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.measurements import Rules
from app.domain.numeric import DomainError
from app.domain.sampling import SamplingSchedule
from app.models import Material, Measurement, MeasurementStatus, Run, RunStatus, User
from app.services.auth_store import auth_transaction
from app.services.auth_types import AuthError, Identity, Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    json_text,
    policy_from,
    require_text,
    snapshot,
    stamp_update,
)


def missing_count(db: Session, run: Run, until: datetime) -> int:
    """Count unfilled scheduled slots and incomplete extra manual samples once each."""
    expected = SamplingSchedule(run.start_time, run.interval_seconds).due_count(until)
    complete = (
        db.scalar(
            select(func.count(Measurement.id)).where(
                Measurement.run_id == run.id,
                Measurement.slot_index.is_not(None),
                Measurement.slot_index < expected,
                Measurement.status != MeasurementStatus.MISSING,
            )
        )
        or 0
    )
    manual_missing = (
        db.scalar(
            select(func.count(Measurement.id)).where(
                Measurement.run_id == run.id,
                Measurement.slot_index.is_(None),
                Measurement.status == MeasurementStatus.MISSING,
            )
        )
        or 0
    )
    return expected - complete + manual_missing


class RunService(ProductionStore):
    """Create and close production runs; no caller can edit a captured standard."""

    def schedule(self, token: str, identifier: int, offset: int = 0, limit: int = 100) -> Document:
        """Read bounded due slots, including virtual missing samples, without production writes."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise DomainError("invalid_page")
        with auth_transaction(self.auth.factory) as db:
            now = self.auth.clock.now()
            actor, _ = self.auth.sessions.require(db, token, now)
            Identity.from_user(actor).require(Permission.RUN_READ)
            run = db.get(Run, identifier)
            if run is None:
                raise DomainError("run_not_found", 404)
            schedule = SamplingSchedule(run.start_time, run.interval_seconds)
            until = run.end_time or now
            total = schedule.due_count(until)
            rows = {
                row.slot_index: row
                for row in db.scalars(
                    select(Measurement).where(
                        Measurement.run_id == run.id,
                        Measurement.slot_index >= offset,
                        Measurement.slot_index < min(offset + limit, total),
                    )
                )
            }
            slots = [
                dict(
                    index=i,
                    due_time=schedule.due_time(i),
                    measurement_id=rows[i].id if i in rows else None,
                    status=rows[i].status.value if i in rows else "missing",
                )
                for i in range(offset, min(offset + limit, total))
            ]
            return Document(
                json_text(
                    dict(
                        id=run.id,
                        revision=run.revision,
                        expected_count=total,
                        missing_count=missing_count(db, run, until),
                        offset=offset,
                        slots=slots,
                    )
                )
            )

    def start(
        self,
        token: str,
        request_id: str,
        material_id: int,
        raw_material_batch: str,
        interval_seconds: int,
    ) -> Document:
        """Start with current active material and policy in one serialized transaction."""

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Copy every rule exactly once and assign server time and a unique run code."""
            batch = require_text(raw_material_batch, 100, "invalid_batch")
            SamplingSchedule(now, interval_seconds)
            material = db.get(Material, material_id)
            if material is None or not material.is_active:
                raise DomainError("material_unavailable", 409)
            settings = self.settings(db)
            policy = policy_from(self.policy(db, settings.accuracy_version_id))
            rules = Rules(**snapshot(material, Rules))
            rules.validate(policy)
            row = Run(
                run_code=f"PL-{now:%Y%m%d%H%M%S}-{uuid4().hex[:12]}",
                material_id=material.id,
                accuracy_version_id=settings.accuracy_version_id,
                raw_material_batch=batch,
                interval_seconds=interval_seconds,
                start_time=now,
                created_by_id=actor.id,
                created_at=now,
                updated_at=now,
                **asdict(rules),
            )
            db.add(row)
            db.flush()
            after = self.run_document(db, row)
            self.audit(db, actor, now, "run_created", "run", row.id, row.run_code, None, after)
            return after

        return self.write(
            token,
            "run.start",
            request_id,
            dict(
                material_id=material_id,
                raw_material_batch=raw_material_batch,
                interval_seconds=interval_seconds,
            ),
            Permission.RUN_CREATE,
            mutate,
        )

    def close(
        self,
        token: str,
        request_id: str,
        identifier: int,
        expected_revision: int,
        exception_reason: str | None = None,
    ) -> Document:
        """Submit eligible production to review, retaining all missing-data evidence."""

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Require Admin authority and a reason for any incomplete or missed samples."""
            row = self.writable_run(db, actor, identifier, expected_revision)
            count = missing_count(db, row, now)
            reason = require_text(exception_reason, 4000) if exception_reason is not None else None
            if count:
                if actor.role.code != "admin":
                    raise AuthError("incomplete_close_requires_admin", 403)
                if reason is None:
                    raise DomainError("closure_exception_reason_required")
            before = self.run_document(db, row)
            row.pending_from, row.status = row.status, RunStatus.PENDING_REVIEW
            row.end_time = now
            stamp_update(row, now)
            row.missing_count_at_close, row.closure_exception_reason = count, reason
            row.revision += 1
            after = self.run_document(db, row)
            self.audit(
                db,
                actor,
                now,
                "run_closed_for_review",
                "run",
                row.id,
                row.run_code,
                before,
                after,
                reason,
            )
            return after

        return self.write(
            token,
            "run.close",
            request_id,
            dict(
                id=identifier,
                expected_revision=expected_revision,
                exception_reason=exception_reason,
            ),
            Permission.RUN_CREATE,
            mutate,
        )

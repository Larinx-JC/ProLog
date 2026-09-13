"""Shared current-authority, transaction, revision, audit and retry handling."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.domain.display import MEASUREMENT_QUANTITIES, RULE_QUANTITIES, DisplayFormatter
from app.domain.measurements import Rules
from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import (
    AccuracyVersion,
    AuditLog,
    DisplaySettings,
    Material,
    Measurement,
    ProductionRequest,
    ProductionSettings,
    Run,
    RunStatus,
    User,
)
from app.services.auth import AuthService
from app.services.auth_store import auth_transaction
from app.services.auth_types import AuthError, Identity, Permission


def _json_value(value: object) -> str:
    """Serialize only exact quantities and UTC event times as public text."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.isoformat(timespec="microseconds") + "Z"
    raise TypeError("Unsupported production data type")


def json_text(value: object) -> str:
    """Canonicalize receipt/audit data without converting exact decimals to floats."""
    return json.dumps(
        value, default=_json_value, sort_keys=True, ensure_ascii=False, allow_nan=False
    )


@dataclass(frozen=True)
class Document:
    """Detached immutable service result; callers can obtain a disposable JSON copy."""

    text: str

    @property
    def id(self) -> int:
        """Read the public entity ID from a service response."""
        return self.as_dict()["id"]

    @property
    def revision(self) -> int:
        """Read the optimistic revision required for a later mutation."""
        return self.as_dict()["revision"]

    def as_dict(self) -> dict:
        """Return a new value tree that cannot mutate a persisted result or ORM row."""
        return json.loads(self.text)


def snapshot(row: object, value_type: type) -> dict:
    """Copy a named domain value object's fields from ORM state exactly once."""
    return {field.name: getattr(row, field.name) for field in fields(value_type)}


def policy_from(row: AccuracyVersion | DisplaySettings) -> AccuracyPolicy:
    """Copy validated precision choices, excluding persistence and lifecycle metadata."""
    return AccuracyPolicy(**snapshot(row, AccuracyPolicy))


class Versioned(Protocol):
    """A production row with an optimistic revision."""

    revision: int


def check_revision(row: Versioned, expected: int | None) -> None:
    """Reject stale edits instead of allowing a later request to overwrite intervening work."""
    if type(expected) is not int or expected != row.revision:
        raise DomainError("revision_conflict", 409)


def require_text(value: object, maximum: int, code: str = "reason_required") -> str:
    """Normalize required user text with explicit empty and storage-size rejection."""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise DomainError(code)
    return value.strip()


def stamp_update(row: Run | Material, now: datetime) -> None:
    """Force the injected timestamp even when two writes share the same clock instant."""
    row.updated_at = now
    flag_modified(row, "updated_at")


class ProductionStore:
    """Serialize factory writes with current auth changes; never accept a stale Identity."""

    def __init__(self, auth: AuthService) -> None:
        """Reuse the established environment, clock, session checker and transaction lock."""
        self.auth = auth

    def write(
        self,
        token: str,
        operation: str,
        request_id: str,
        payload: dict,
        permission: Permission,
        mutate: Callable[[Session, User, datetime], dict],
    ) -> Document:
        """Atomically commit a mutation, its audit, and a durable actor-scoped retry receipt."""
        try:
            key = str(UUID(request_id))
        except (ValueError, AttributeError, TypeError) as error:
            raise DomainError("invalid_request_id") from error
        try:
            digest = hashlib.sha256(json_text(payload).encode("utf-8")).hexdigest()
        except (TypeError, ValueError) as error:
            raise DomainError("invalid_request_payload") from error
        with auth_transaction(self.auth.factory) as db:
            now = self.auth.clock.now()
            actor, _ = self.auth.sessions.require(db, token, now, activity=True)
            Identity.from_user(actor).require(permission)
            previous = db.get(ProductionRequest, (actor.id, key))
            if previous:
                if previous.operation != operation or previous.payload_digest != digest:
                    raise DomainError("request_conflict", 409)
                return Document(json_text(previous.result))
            result = mutate(db, actor, now)
            db.flush()
            # JSON round-trip guarantees the same public types on first result and retry.
            result = json.loads(json_text(result))
            db.add(
                ProductionRequest(
                    actor_id=actor.id,
                    request_id=key,
                    operation=operation,
                    payload_digest=digest,
                    result=result,
                    created_at=now,
                )
            )
            return Document(json_text(result))

    @staticmethod
    def settings(db: Session) -> ProductionSettings:
        """Fail explicitly if required migration seed configuration is missing."""
        row = db.get(ProductionSettings, 1)
        if row is None:
            raise DomainError("production_unavailable", 503)
        return row

    @staticmethod
    def policy(db: Session, identifier: int | None) -> AccuracyVersion:
        """Resolve the referenced immutable policy, never silently substitute current settings."""
        row = db.get(AccuracyVersion, identifier) if identifier is not None else None
        if row is None:
            raise DomainError("accuracy_policy_unavailable", 409)
        return row

    @staticmethod
    def display_settings(db: Session) -> DisplaySettings:
        """Require the migrated current presentation settings instead of guessing preferences."""
        row = db.get(DisplaySettings, 1)
        if row is None:
            raise DomainError("display_settings_unavailable", 503)
        return row

    def display_document(self, db: Session) -> dict:
        """Describe one consistent presentation revision for readers and Admin audit records."""
        row = self.display_settings(db)
        return dict(
            id=1,
            revision=row.revision,
            precision=asdict(policy_from(row)),
            updated_at=row.updated_at,
            updated_by_id=row.updated_by_id,
        )

    def writable_run(self, db: Session, actor: User, identifier: int, expected: int) -> Run:
        """Apply ownership, current abnormal-work settings, legacy and lifecycle protections."""
        row = db.get(Run, identifier)
        if row is None:
            raise DomainError("run_not_found", 404)
        if not Identity.from_user(actor).can_edit_run(row.created_by_id):
            raise AuthError("permission_denied", 403)
        if row.status not in {RunStatus.ACTIVE, RunStatus.ABNORMAL}:
            raise DomainError("run_not_editable", 409)
        if any(
            value is not None
            for value in (
                row.end_time,
                row.pending_from,
                row.reviewed_at,
                row.reviewed_by_id,
                row.review_resolution,
                row.review_reason,
                row.missing_count_at_close,
                row.closure_exception_reason,
            )
        ):
            raise DomainError("inconsistent_active_state", 409)
        if self.auth.clock.now() < row.updated_at:
            raise DomainError("server_clock_moved_backwards", 409)
        if (
            row.status == RunStatus.ABNORMAL
            and actor.role.code != "admin"
            and not self.settings(db).operator_abnormal_allowed
        ):
            raise AuthError("permission_denied", 403)
        if self.policy(db, row.accuracy_version_id).calculation_version != "target_v1":
            raise DomainError("legacy_run_read_only", 409)
        check_revision(row, expected)
        return row

    @staticmethod
    def audit(
        db: Session,
        actor: User,
        now: datetime,
        action: str,
        target_type: str,
        target_id: int,
        label: str,
        before: dict | None,
        after: dict,
        reason: str | None = None,
    ) -> None:
        """Stage full before/after data alongside its mutation without committing independently."""
        db.add(
            AuditLog(
                occurred_at=now,
                actor_id=actor.id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_label=label,
                before_value=json_text(before) if before is not None else None,
                after_value=json_text(after),
                reason=reason,
            )
        )

    def run_document(self, db: Session, run: Run) -> dict:
        """Return immutable-history metadata and explicit completeness for future readers."""
        version = self.policy(db, run.accuracy_version_id)
        return {
            "id": run.id,
            "revision": run.revision,
            "run_code": run.run_code,
            "material_id": run.material_id,
            "raw_material_batch": run.raw_material_batch,
            "created_by_id": run.created_by_id,
            "status": run.status.value,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "interval_seconds": run.interval_seconds,
            "accuracy_version_id": version.id,
            "accuracy": asdict(policy_from(version)),
            "calculation_version": version.calculation_version,
            "rules": formatted_rules(run, policy_from(version)),
            "pending_from": run.pending_from.value if run.pending_from else None,
            "review_resolution": run.review_resolution.value if run.review_resolution else None,
            "review_reason": run.review_reason,
            "reviewed_by_id": run.reviewed_by_id,
            "reviewed_at": run.reviewed_at,
            "missing_count_at_close": run.missing_count_at_close,
            "closure_exception_reason": run.closure_exception_reason,
        }

    def get_run(self, token: str, identifier: int) -> Document:
        """Read an authorized run without counting background monitoring as user activity."""
        with auth_transaction(self.auth.factory) as db:
            actor, _ = self.auth.sessions.require(db, token, self.auth.clock.now())
            Identity.from_user(actor).require(Permission.RUN_READ)
            row = db.get(Run, identifier)
            if row is None:
                raise DomainError("run_not_found", 404)
            result = self.run_document(db, row)
            policy = policy_from(self.policy(db, row.accuracy_version_id))
            result["measurements"] = [
                self.measurement_document(m, policy)
                for m in db.scalars(
                    select(Measurement)
                    .where(Measurement.run_id == identifier)
                    .order_by(Measurement.measurement_time, Measurement.id)
                )
            ]
            from app.services.production.runs import missing_count

            result["missing_count"] = (
                None
                if result["calculation_version"] == "legacy"
                else row.missing_count_at_close
                if row.end_time is not None
                else missing_count(db, row, self.auth.clock.now())
            )
            presentation = self.display_document(db)
            formatter = DisplayFormatter(AccuracyPolicy(**presentation["precision"]))
            result["display"] = dict(
                settings=presentation, rules=formatter.project(result["rules"], RULE_QUANTITIES)
            )
            for measurement in result["measurements"]:
                measurement["display"] = formatter.project(measurement, MEASUREMENT_QUANTITIES)
            return Document(json_text(result))

    @staticmethod
    def measurement_document(row: Measurement, policy: AccuracyPolicy) -> dict:
        """Format each physical value and result using its run's captured precision."""
        values = {}
        for name, group in MEASUREMENT_QUANTITIES.items():
            value = getattr(row, name)
            values[name] = policy.format(value, group) if value is not None else None
        return dict(
            id=row.id,
            revision=row.revision,
            run_id=row.run_id,
            slot_index=row.slot_index,
            measurement_time=row.measurement_time,
            recorded_at=row.recorded_at,
            recorded_by_id=row.recorded_by_id,
            status=row.status.value,
            alarm_codes=row.alarm_codes or [],
            entry_method=row.entry_method.value,
            **values,
        )


def formatted_rules(row: object, policy: AccuracyPolicy) -> dict:
    """Format a material or captured run rule set using one shared field/unit mapping."""
    values = snapshot(row, Rules)
    for name, group in RULE_QUANTITIES.items():
        values[name] = policy.format(values[name], group)
    return values

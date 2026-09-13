"""Bounded authorized read queries for production APIs; every write stays in domain services."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.display import MEASUREMENT_QUANTITIES, RULE_QUANTITIES, DisplayFormatter
from app.domain.measurements import Rules
from app.domain.numeric import AccuracyPolicy, DomainError
from app.domain.sampling import FACTORY_TIMEZONE
from app.models import AuditLog, Material, Measurement, Run, RunStatus
from app.services.auth_store import auth_transaction
from app.services.auth_types import Identity, Permission
from app.services.production.base import Document, ProductionStore, json_text, policy_from, snapshot
from app.services.production.runs import missing_count


def validate_page(offset: int, limit: int) -> None:
    """Enforce materialization bounds even when a caller bypasses the HTTP validators."""
    if type(offset) is not int or not 0 <= offset <= 2147483647:
        raise DomainError("invalid_page")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise DomainError("invalid_page")


def page(items: list[dict], offset: int, limit: int, total: int) -> dict:
    """Describe the limited result without implying that total rows were materialized."""
    return dict(
        items=items, offset=offset, limit=limit, total=total, has_more=offset + len(items) < total
    )


def exact_material_value(value: Decimal) -> str:
    """Remove database padding zeros without rounding meaningful recorded fractional digits."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class ProductionReadService(ProductionStore):
    """Return detached read contracts under one current-authority transaction per response."""

    @contextmanager
    def read(self, token: str, permission: Permission) -> Iterator[tuple[Session, datetime]]:
        """Recheck current sessions and roles; monitoring reads never renew idle expiry."""
        with auth_transaction(self.auth.factory) as db:
            now = self.auth.clock.now()
            actor, _ = self.auth.sessions.require(db, token, now)
            Identity.from_user(actor).require(permission)
            yield db, now

    def _run(self, db: Session, identifier: int) -> Run:
        """Resolve a parent without loading its relationship collection."""
        row = db.get(Run, identifier)
        if row is None:
            raise DomainError("run_not_found", 404)
        return row

    def _present_run(self, db: Session, row: Run, display: dict) -> dict:
        """Reuse captured canonical serialization with the response's current display revision."""
        result = self.run_document(db, row)
        formatter = DisplayFormatter(AccuracyPolicy(**display["precision"]))
        result["display"] = dict(
            settings=display, rules=formatter.project(result["rules"], RULE_QUANTITIES)
        )
        return result

    def runs(self, token: str, offset: int = 0, limit: int = 50) -> Document:
        """List runs newest-first with an ID tie-breaker and no nested measurements."""
        validate_page(offset, limit)
        with self.read(token, Permission.RUN_READ) as (db, _):
            display = self.display_document(db)
            rows = db.scalars(
                select(Run)
                .order_by(Run.start_time.desc(), Run.id.desc())
                .offset(offset)
                .limit(limit)
            )
            total = db.scalar(select(func.count(Run.id))) or 0
            return Document(
                json_text(
                    page([self._present_run(db, r, display) for r in rows], offset, limit, total)
                )
            )

    def run(self, token: str, identifier: int) -> Document:
        """Return one bounded detail record and compute completeness through aggregate queries."""
        with self.read(token, Permission.RUN_READ) as (db, now):
            row = self._run(db, identifier)
            result = self._present_run(db, row, self.display_document(db))
            result["measurement_count"] = (
                db.scalar(
                    select(func.count(Measurement.id)).where(Measurement.run_id == identifier)
                )
                or 0
            )
            result["missing_count"] = (
                None
                if result["calculation_version"] == "legacy"
                else row.missing_count_at_close
                if row.end_time is not None
                else missing_count(db, row, now)
            )
            return Document(json_text(result))

    def measurements(self, token: str, run_id: int, offset: int = 0, limit: int = 50) -> Document:
        """Read only the selected parent's bounded samples, with one display policy per page."""
        validate_page(offset, limit)
        with self.read(token, Permission.RUN_READ) as (db, _):
            run = self._run(db, run_id)
            version = self.policy(db, run.accuracy_version_id)
            policy = policy_from(version)
            display = self.display_document(db)
            formatter = DisplayFormatter(AccuracyPolicy(**display["precision"]))
            rows = db.scalars(
                select(Measurement)
                .where(Measurement.run_id == run_id)
                .order_by(Measurement.measurement_time, Measurement.id)
                .offset(offset)
                .limit(limit)
            )
            total = (
                db.scalar(select(func.count(Measurement.id)).where(Measurement.run_id == run_id))
                or 0
            )
            items = []
            for row in rows:
                item = self.measurement_document(row, policy)
                item["display"] = formatter.project(item, MEASUREMENT_QUANTITIES)
                items.append(item)
            result = dict(
                page(items, offset, limit, total),
                run_id=run_id,
                run_revision=run.revision,
                accuracy=asdict(policy),
                calculation_version=version.calculation_version,
                display_settings=display,
            )
            return Document(json_text(result))

    def _material(self, row: Material, display: dict) -> dict:
        """Serialize persisted rules exactly, including inactive standards at older precision."""
        rules = {
            name: exact_material_value(value) if isinstance(value, Decimal) else value
            for name, value in snapshot(row, Rules).items()
        }
        formatter = DisplayFormatter(AccuracyPolicy(**display["precision"]))
        return dict(
            id=row.id,
            revision=row.revision,
            material_no=row.material_no,
            is_active=row.is_active,
            rules=rules,
            display=dict(settings=display, rules=formatter.project(rules, RULE_QUANTITIES)),
        )

    def materials(self, token: str, offset: int = 0, limit: int = 50) -> Document:
        """List named standards, retaining inactive records for history and Admin editing."""
        validate_page(offset, limit)
        with self.read(token, Permission.MATERIAL_READ) as (db, _):
            display = self.display_document(db)
            rows = db.scalars(select(Material).order_by(Material.id).offset(offset).limit(limit))
            total = db.scalar(select(func.count(Material.id))) or 0
            return Document(
                json_text(page([self._material(r, display) for r in rows], offset, limit, total))
            )

    def material(self, token: str, identifier: int) -> Document:
        """Return exact current rules with separate display values to a permitted reader."""
        with self.read(token, Permission.MATERIAL_READ) as (db, _):
            row = db.get(Material, identifier)
            if row is None:
                raise DomainError("material_not_found", 404)
            return Document(json_text(self._material(row, self.display_document(db))))

    def audits(self, token: str, offset: int = 0, limit: int = 50) -> Document:
        """Expose original audit payloads to Admin/Reviewer only, in descending event-ID order."""
        validate_page(offset, limit)
        with self.read(token, Permission.AUDIT_READ) as (db, _):
            rows = db.scalars(
                select(AuditLog).order_by(AuditLog.id.desc()).offset(offset).limit(limit)
            )
            names = (
                "id",
                "occurred_at",
                "action",
                "actor_id",
                "target_type",
                "target_id",
                "target_label",
                "before_value",
                "after_value",
                "reason",
            )
            items = [{name: getattr(row, name) for name in names} for row in rows]
            total = db.scalar(select(func.count(AuditLog.id))) or 0
            return Document(json_text(page(items, offset, limit, total)))

    def overview(self, token: str) -> Document:
        """Count all current statuses and today's starts using Shanghai calendar boundaries."""
        with self.read(token, Permission.RUN_READ) as (db, now):
            day = now.replace(tzinfo=UTC).astimezone(FACTORY_TIMEZONE).date()
            start = (
                datetime.combine(day, time.min, FACTORY_TIMEZONE)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            end = start + timedelta(days=1)
            counts = {status.value: 0 for status in RunStatus}
            counts.update(
                {
                    status.value: count
                    for status, count in db.execute(
                        select(Run.status, func.count(Run.id)).group_by(Run.status)
                    )
                }
            )
            today = (
                db.scalar(
                    select(func.count(Run.id)).where(Run.start_time >= start, Run.start_time < end)
                )
                or 0
            )
            display = self.display_document(db)
            recent = db.scalars(select(Run).order_by(Run.start_time.desc(), Run.id.desc()).limit(5))
            return Document(
                json_text(
                    dict(
                        as_of=now,
                        factory_timezone="Asia/Shanghai",
                        factory_date=day.isoformat(),
                        today_started_runs=today,
                        total_runs=sum(counts.values()),
                        status_counts=counts,
                        recent_runs=[self._present_run(db, r, display) for r in recent],
                    )
                )
            )

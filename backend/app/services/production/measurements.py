"""Production measurements use captured rules and commit alarms with their run state."""

from dataclasses import asdict, fields
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.measurements import AbnormalityDetector, MeasurementCalculator, Readings, Rules
from app.domain.numeric import AccuracyPolicy, DomainError
from app.domain.sampling import ProductionTime, SamplingSchedule
from app.models import Measurement, MeasurementStatus, RunStatus, User
from app.services.auth_types import Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    check_revision,
    policy_from,
    require_text,
    snapshot,
    stamp_update,
)


def parse_readings(values: dict, policy: AccuracyPolicy) -> Readings:
    """Reject forged calculated/identity fields and validate every supplied input string."""
    allowed = {field.name for field in fields(Readings)}
    if not isinstance(values, dict) or set(values) - allowed:
        raise DomainError("unknown_measurement_field")
    parsed = {}
    for name in allowed:
        group = (
            "resistance"
            if name.startswith("point_")
            else {
                "thickness": "thickness",
                "meter_count": "length",
                "speed": "speed",
            }[name]
        )
        value = values.get(name)
        parsed[name] = policy.parse(value, group) if value is not None else None
    return Readings(**parsed)


class MeasurementService(ProductionStore):
    """Write only eligible owner/Admin measurements; every input path must reuse this service."""

    def save(
        self,
        token: str,
        request_id: str,
        run_id: int,
        expected_run_revision: int,
        measurement_time: str,
        values: dict,
        slot_index: int | None = None,
        measurement_id: int | None = None,
        expected_revision: int | None = None,
        reason: str | None = None,
    ) -> Document:
        """Save partial/complete samples or audited corrections without bypassing any run rule."""
        payload = dict(
            run_id=run_id,
            expected_run_revision=expected_run_revision,
            measurement_time=measurement_time,
            values=values,
            slot_index=slot_index,
            measurement_id=measurement_id,
            expected_revision=expected_revision,
            reason=reason,
        )

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Apply readings, computations, sticky abnormality and both audit events atomically."""
            run = self.writable_run(db, actor, run_id, expected_run_revision)
            policy = policy_from(self.policy(db, run.accuracy_version_id))
            rules = Rules(**snapshot(run, Rules))
            observed = ProductionTime.parse(measurement_time)
            ProductionTime.validate(observed, run.start_time, now)
            if slot_index is not None:
                SamplingSchedule(run.start_time, run.interval_seconds).validate_slot(
                    slot_index, observed, now
                )
            readings = parse_readings(values, policy)
            row = db.get(Measurement, measurement_id) if measurement_id is not None else None
            before = None
            explanation = require_text(reason, 4000) if reason is not None else None
            if measurement_id is not None:
                if row is None or row.run_id != run.id:
                    raise DomainError("measurement_not_found", 404)
                check_revision(row, expected_revision)
                if row.slot_index != slot_index:
                    raise DomainError("sample_identity_immutable", 409)
                explanation = require_text(reason, 4000)
                before = self.measurement_document(row, policy)
                row.revision += 1
            else:
                if (
                    slot_index is not None
                    and db.scalar(
                        select(Measurement.id).where(
                            Measurement.run_id == run.id,
                            Measurement.slot_index == slot_index,
                        )
                    )
                    is not None
                ):
                    raise DomainError("sample_already_exists", 409)
                row = Measurement(run_id=run.id, slot_index=slot_index)
                db.add(row)
            for name, value in asdict(readings).items():
                setattr(row, name, value)
            row.measurement_time, row.recorded_at, row.recorded_by_id = observed, now, actor.id
            row.alarm_codes = list(AbnormalityDetector.evaluate(readings, rules, policy))
            stats = MeasurementCalculator.calculate(readings, rules, policy)
            row.average_value = stats.average if stats else None
            row.max_deviation = stats.max_uniformity_deviation if stats else None
            row.deviation_percent = stats.uniformity_percent if stats else None
            row.target_deviation = stats.max_target_deviation if stats else None
            row.target_deviation_percent = stats.target_deviation_percent if stats else None
            row.status = (
                MeasurementStatus.MISSING
                if readings.missing(rules)
                else MeasurementStatus.ABNORMAL
                if row.alarm_codes
                else MeasurementStatus.COMPLETED
            )
            old_run = self.run_document(db, run)
            newly_abnormal = bool(row.alarm_codes) and run.status == RunStatus.ACTIVE
            if row.alarm_codes:
                run.status = RunStatus.ABNORMAL
            run.revision += 1
            stamp_update(run, now)
            db.flush()
            result = self.measurement_document(row, policy)
            result["run_revision"], result["run_status"] = run.revision, run.status.value
            result["missing_fields"] = list(readings.missing(rules))
            self.audit(
                db,
                actor,
                now,
                "measurement_corrected" if before else "measurement_recorded",
                "measurement",
                row.id,
                run.run_code,
                before,
                result,
                explanation,
            )
            if newly_abnormal:
                self.audit(
                    db,
                    actor,
                    now,
                    "run_marked_abnormal",
                    "run",
                    run.id,
                    run.run_code,
                    old_run,
                    self.run_document(db, run),
                )
            return result

        return self.write(
            token, "measurement.save", request_id, payload, Permission.RUN_CREATE, mutate
        )

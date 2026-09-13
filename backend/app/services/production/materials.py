"""Current material rules with exact validation, audited edits and soft deactivation."""

from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.measurements import Rules
from app.domain.numeric import AccuracyPolicy, DomainError
from app.models import Material, User
from app.services.auth_types import Permission
from app.services.production.base import (
    Document,
    ProductionStore,
    check_revision,
    formatted_rules,
    policy_from,
    require_text,
    snapshot,
    stamp_update,
)


def parse_rules(values: dict, policy: AccuracyPolicy) -> Rules:
    """Accept only material input fields, with the approved initial deviation tolerance."""
    numeric = {
        "standard_value": "resistance",
        "upper_limit": "resistance",
        "lower_limit": "resistance",
        "thickness_min": "thickness",
        "thickness_max": "thickness",
        "deviation_pct_threshold": "result",
    }
    switches = {"deviation_check_enabled", "thickness_check_enabled", "limits_check_enabled"}
    if not isinstance(values, dict) or set(values) - set(numeric) - switches:
        raise DomainError("unknown_rule_field")
    values = dict(values)
    values.setdefault(
        "deviation_pct_threshold",
        policy.format(Decimal("2.00")),
    )
    if set(numeric) - values.keys():
        raise DomainError("missing_rule_field")
    parsed: dict = {
        name: policy.parse(values[name], group, positive=name == "standard_value")
        for name, group in numeric.items()
    }
    rules = Rules(**parsed, **{name: values.get(name, True) for name in switches})
    rules.validate(policy)
    return rules


def material_document(row: Material, policy: AccuracyPolicy) -> dict:
    """Return exact material values formatted with the current factory policy."""
    values = formatted_rules(row, policy)
    return dict(
        id=row.id,
        revision=row.revision,
        material_no=row.material_no,
        is_active=row.is_active,
        rules=values,
    )


class MaterialService(ProductionStore):
    """Own every material mutation; runs never look up these mutable rules for evaluation."""

    def create(self, token: str, request_id: str, material_no: str, values: dict) -> Document:
        """Create an active material with validated rules and a complete audit event."""

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Check uniqueness under the common writer lock before persisting."""
            name = require_text(material_no, 50, "invalid_material_no")
            if db.scalar(select(Material.id).where(Material.material_no == name)) is not None:
                raise DomainError("material_exists", 409)
            policy = policy_from(self.policy(db, self.settings(db).accuracy_version_id))
            rules = parse_rules(values, policy)
            row = Material(material_no=name, **asdict(rules), created_at=now, updated_at=now)
            db.add(row)
            db.flush()
            result = material_document(row, policy)
            self.audit(db, actor, now, "material_created", "material", row.id, name, None, result)
            return result

        return self.write(
            token,
            "material.create",
            request_id,
            dict(material_no=material_no, values=values),
            Permission.MATERIAL_MANAGE,
            mutate,
        )

    def update(
        self,
        token: str,
        request_id: str,
        identifier: int,
        expected_revision: int,
        values: dict,
        is_active: bool,
        reason: str,
    ) -> Document:
        """Replace validated rules and activation state while preserving every run snapshot."""

        def mutate(db: Session, actor: User, now: datetime) -> dict:
            """Reject missing/stale materials, and audit the exact old and new rules."""
            row = db.get(Material, identifier)
            if row is None:
                raise DomainError("material_not_found", 404)
            check_revision(row, expected_revision)
            explanation = require_text(reason, 4000)
            if type(is_active) is not bool:
                raise DomainError("invalid_active_flag")
            policy = policy_from(self.policy(db, self.settings(db).accuracy_version_id))
            rules = parse_rules(values, policy)
            # Old values must remain exact in the audit even if inactive standards
            # need replacing to satisfy a newly selected lower precision.
            before = dict(
                id=row.id,
                revision=row.revision,
                material_no=row.material_no,
                is_active=row.is_active,
                rules=snapshot(row, Rules),
            )
            for name, value in asdict(rules).items():
                setattr(row, name, value)
            row.is_active = is_active
            stamp_update(row, now)
            row.revision += 1
            after = material_document(row, policy)
            self.audit(
                db,
                actor,
                now,
                "material_updated",
                "material",
                row.id,
                row.material_no,
                before,
                after,
                explanation,
            )
            return after

        return self.write(
            token,
            "material.update",
            request_id,
            dict(
                id=identifier,
                expected_revision=expected_revision,
                values=values,
                is_active=is_active,
                reason=reason,
            ),
            Permission.MATERIAL_MANAGE,
            mutate,
        )

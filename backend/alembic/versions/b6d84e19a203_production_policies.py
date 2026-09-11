"""Versioned accuracy, six-place storage, sampling and production concurrency.

Revision ID: b6d84e19a203
Revises: 7a9b31c4d502
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "b6d84e19a203"
down_revision = "7a9b31c4d502"
branch_labels = None
depends_on = None

_TIME = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")
_NUMBER = sa.Numeric(24, 6)
_RULE_NUMBERS = (
    "standard_value",
    "upper_limit",
    "lower_limit",
    "thickness_min",
    "thickness_max",
    "deviation_pct_threshold",
)
_MEASUREMENT_NUMBERS = (
    "meter_count",
    "speed",
    "point_1",
    "point_2",
    "point_3",
    "point_4",
    "thickness",
    "average_value",
    "max_deviation",
    "deviation_percent",
)
_TIMES = {
    "users": ("created_at", "updated_at"),
    "materials": ("created_at", "updated_at"),
    "runs": ("start_time", "end_time", "reviewed_at", "created_at", "updated_at"),
    "measurements": ("measurement_time", "recorded_at"),
    "audit_logs": ("occurred_at",),
}


def _alter_storage(up: bool) -> None:
    """Preserve named checks while changing precision on SQLite and MySQL."""
    for table, times in _TIMES.items():
        numbers = _RULE_NUMBERS if table in {"materials", "runs"} else ()
        if table == "measurements":
            numbers = _MEASUREMENT_NUMBERS
        constraints = []
        if table in {"materials", "runs"}:
            constraints = [
                (f"ck_{table}_limits_order", "lower_limit <= upper_limit"),
                (f"ck_{table}_thickness_order", "thickness_min <= thickness_max"),
                (f"ck_{table}_deviation_nonneg", "deviation_pct_threshold >= 0"),
            ]
        if table == "runs":
            constraints.append(
                ("ck_runs_end_after_start", "end_time IS NULL OR end_time >= start_time")
            )
        with op.batch_alter_table(table) as batch:
            for name, _ in constraints:
                batch.drop_constraint(name, type_="check")
            for name in numbers:
                batch.alter_column(
                    name,
                    existing_type=sa.Numeric(10, 2) if up else _NUMBER,
                    type_=_NUMBER if up else sa.Numeric(10, 2),
                    existing_nullable=table == "measurements",
                )
            for name in times:
                batch.alter_column(
                    name,
                    existing_type=sa.DateTime() if up else _TIME,
                    type_=_TIME if up else sa.DateTime(),
                    existing_nullable=name in {"end_time", "reviewed_at", "recorded_at"},
                )
            for name, expression in constraints:
                batch.create_check_constraint(name, expression)


def upgrade() -> None:
    """Preserve existing values and interpretation while adding new production policies."""
    op.create_table(
        "accuracy_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        *(
            sa.Column(f"{name}_places", sa.Integer, nullable=False)
            for name in ("resistance", "thickness", "speed", "length", "result")
        ),
        sa.Column("rounding", sa.String(16), nullable=False),
        sa.Column("calculation_version", sa.String(16), nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *(
            sa.CheckConstraint(f"{name}_places BETWEEN 0 AND 6", name=f"ck_accuracy_{name}")
            for name in ("resistance", "thickness", "speed", "length", "result")
        ),
        sa.CheckConstraint("rounding IN ('half_up', 'half_even')", name="ck_accuracy_rounding"),
    )
    versions = sa.table(
        "accuracy_versions",
        sa.column("id", sa.Integer),
        *(
            sa.column(f"{name}_places", sa.Integer)
            for name in ("resistance", "thickness", "speed", "length", "result")
        ),
        sa.column("rounding", sa.String),
        sa.column("calculation_version", sa.String),
        sa.column("created_at", _TIME),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        versions,
        [
            dict(
                id=identifier,
                resistance_places=2,
                thickness_places=thickness,
                speed_places=2,
                length_places=2,
                result_places=2,
                rounding="half_up",
                calculation_version=version,
                created_at=now,
            )
            for identifier, thickness, version in ((1, 2, "legacy"), (2, 3, "target_v1"))
        ],
    )
    op.create_table(
        "production_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column(
            "accuracy_version_id", sa.Integer, sa.ForeignKey("accuracy_versions.id"), nullable=False
        ),
        sa.Column(
            "operator_abnormal_allowed", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("id = 1", name="ck_production_settings_singleton"),
        sa.CheckConstraint("revision > 0", name="ck_production_settings_revision"),
    )
    op.execute("INSERT INTO production_settings (id, accuracy_version_id) VALUES (1, 2)")
    _alter_storage(True)
    with op.batch_alter_table("materials") as batch:
        batch.add_column(sa.Column("revision", sa.Integer, nullable=False, server_default="1"))
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("revision", sa.Integer, nullable=False, server_default="1"))
        batch.add_column(sa.Column("accuracy_version_id", sa.Integer, nullable=True))
        batch.create_foreign_key(
            "fk_runs_accuracy_version", "accuracy_versions", ["accuracy_version_id"], ["id"]
        )
        batch.add_column(sa.Column("missing_count_at_close", sa.Integer, nullable=True))
        batch.add_column(sa.Column("closure_exception_reason", sa.Text, nullable=True))
    op.execute("UPDATE runs SET accuracy_version_id = 1")
    with op.batch_alter_table("measurements") as batch:
        batch.add_column(sa.Column("revision", sa.Integer, nullable=False, server_default="1"))
        batch.add_column(sa.Column("slot_index", sa.Integer, nullable=True))
        batch.add_column(sa.Column("alarm_codes", sa.JSON, nullable=True))
        batch.add_column(sa.Column("target_deviation", _NUMBER, nullable=True))
        batch.add_column(sa.Column("target_deviation_percent", _NUMBER, nullable=True))
        batch.create_unique_constraint("uq_measurement_run_slot", ["run_id", "slot_index"])
        batch.create_check_constraint(
            "ck_measurement_slot", "slot_index IS NULL OR slot_index >= 0"
        )
    op.create_table(
        "production_requests",
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
    )


def downgrade() -> None:
    """Refuse lossy numeric narrowing before removing any Section 4 schema."""
    for table, names in (
        ("materials", _RULE_NUMBERS),
        ("runs", _RULE_NUMBERS),
        ("measurements", _MEASUREMENT_NUMBERS),
    ):
        for name in names:
            incompatible = op.get_bind().scalar(
                sa.text(
                    f"SELECT COUNT(*) FROM {table} WHERE {name} != ROUND({name}, 2) "
                    f"OR ABS({name}) > 99999999.99"
                )
            )
            if incompatible:
                raise RuntimeError("Cannot downgrade production precision without losing data")
    op.drop_table("production_requests")
    if op.get_bind().dialect.name == "mysql":
        # InnoDB may replace its implicit run_id FK index with our composite
        # unique index. Restore support before dropping that composite index.
        indexes = sa.inspect(op.get_bind()).get_indexes("measurements")
        if not any(
            index["name"] != "uq_measurement_run_slot"
            and index["column_names"][:1] == ["run_id"]
            for index in indexes
        ):
            op.create_index("run_id", "measurements", ["run_id"])
    with op.batch_alter_table("measurements") as batch:
        batch.drop_constraint("uq_measurement_run_slot", type_="unique")
        batch.drop_constraint("ck_measurement_slot", type_="check")
        for name in (
            "revision",
            "slot_index",
            "alarm_codes",
            "target_deviation",
            "target_deviation_percent",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("fk_runs_accuracy_version", type_="foreignkey")
        for name in (
            "revision",
            "accuracy_version_id",
            "missing_count_at_close",
            "closure_exception_reason",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("materials") as batch:
        batch.drop_column("revision")
    _alter_storage(False)
    op.drop_table("production_settings")
    op.drop_table("accuracy_versions")

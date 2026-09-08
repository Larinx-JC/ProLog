"""initial schema

Revision ID: 0c3dff882627
Revises:
Create Date: 2026-08-17 01:22:30.339118

Hand-written (no local MySQL available for autogenerate); values for enum
columns are inlined as literals rather than imported from app.models.enums
deliberately -- migrations are a frozen historical record, and importing
the live enum would make this file's DDL silently drift if that enum is
ever changed by a later migration.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0c3dff882627'
down_revision = None
branch_labels = None
depends_on = None

_DECIMAL = sa.Numeric(10, 2)
_RUN_STATUS = sa.Enum(
    "active", "abnormal", "pending_review", "reviewed", name="run_status"
)
_MEASUREMENT_STATUS = sa.Enum(
    "missing", "completed", "abnormal", name="measurement_status"
)
_REVIEW_RESOLUTION = sa.Enum(
    "approved", "confirmed_abnormal", "false_alarm", name="review_resolution"
)
_ENTRY_METHOD = sa.Enum("manual", "automated", name="entry_method")


def upgrade() -> None:
    """Create the initial production schema and fixed reference-role rows."""
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
    )
    op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("account", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "must_change_password", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        # created_at/updated_at have no server_default: the app always
        # supplies app.core.time.utcnow() explicitly (see TimestampMixin),
        # so correctness doesn't depend on the MySQL server's timezone.
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_users_account", "users", ["account"], unique=True)

    op.create_table(
        "materials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_no", sa.String(50), nullable=False),
        sa.Column("standard_value", _DECIMAL, nullable=False),
        sa.Column("upper_limit", _DECIMAL, nullable=False),
        sa.Column("lower_limit", _DECIMAL, nullable=False),
        sa.Column("thickness_min", _DECIMAL, nullable=False),
        sa.Column("thickness_max", _DECIMAL, nullable=False),
        sa.Column(
            "deviation_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("deviation_pct_threshold", _DECIMAL, nullable=False),
        sa.Column(
            "thickness_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("limits_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("lower_limit <= upper_limit", name="ck_materials_limits_order"),
        sa.CheckConstraint(
            "thickness_min <= thickness_max", name="ck_materials_thickness_order"
        ),
        sa.CheckConstraint(
            "deviation_pct_threshold >= 0", name="ck_materials_deviation_nonneg"
        ),
    )
    op.create_index("ix_materials_material_no", "materials", ["material_no"], unique=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_code", sa.String(64), nullable=False),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id"), nullable=False),
        # Full snapshot of the Material's abnormality rules at creation
        # time (mirrors materials' rule columns above) -- always read
        # from here, never re-looked-up from the live Material, so an
        # edit to the material's rules can never retroactively change how
        # this run's measurements (including ones added after the edit,
        # while this run is still active) are judged.
        sa.Column("standard_value", _DECIMAL, nullable=False),
        sa.Column("upper_limit", _DECIMAL, nullable=False),
        sa.Column("lower_limit", _DECIMAL, nullable=False),
        sa.Column("thickness_min", _DECIMAL, nullable=False),
        sa.Column("thickness_max", _DECIMAL, nullable=False),
        sa.Column(
            "deviation_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("deviation_pct_threshold", _DECIMAL, nullable=False),
        sa.Column(
            "thickness_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("limits_check_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("raw_material_batch", sa.String(100), nullable=False),
        sa.Column("interval_seconds", sa.Integer, nullable=False),
        sa.Column("status", _RUN_STATUS, nullable=False, server_default="active"),
        sa.Column("pending_from", _RUN_STATUS, nullable=True),
        sa.Column("start_time", sa.DateTime, nullable=False),
        sa.Column("end_time", sa.DateTime, nullable=True),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("review_resolution", _REVIEW_RESOLUTION, nullable=True),
        sa.Column("review_reason", sa.Text, nullable=True),
        sa.Column("reviewed_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("lower_limit <= upper_limit", name="ck_runs_limits_order"),
        sa.CheckConstraint("thickness_min <= thickness_max", name="ck_runs_thickness_order"),
        sa.CheckConstraint("deviation_pct_threshold >= 0", name="ck_runs_deviation_nonneg"),
        sa.CheckConstraint("interval_seconds > 0", name="ck_runs_interval_positive"),
        sa.CheckConstraint(
            "pending_from IS NULL OR pending_from IN ('active', 'abnormal')",
            name="ck_runs_pending_from_valid",
        ),
        sa.CheckConstraint(
            "end_time IS NULL OR end_time >= start_time", name="ck_runs_end_after_start"
        ),
    )
    op.create_index("ix_runs_run_code", "runs", ["run_code"], unique=True)

    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("measurement_time", sa.DateTime, nullable=False),
        sa.Column("meter_count", _DECIMAL, nullable=True),
        sa.Column("speed", _DECIMAL, nullable=True),
        sa.Column("point_1", _DECIMAL, nullable=True),
        sa.Column("point_2", _DECIMAL, nullable=True),
        sa.Column("point_3", _DECIMAL, nullable=True),
        sa.Column("point_4", _DECIMAL, nullable=True),
        sa.Column("thickness", _DECIMAL, nullable=True),
        sa.Column("average_value", _DECIMAL, nullable=True),
        sa.Column("max_deviation", _DECIMAL, nullable=True),
        sa.Column("deviation_percent", _DECIMAL, nullable=True),
        sa.Column(
            "status", _MEASUREMENT_STATUS, nullable=False, server_default="missing"
        ),
        sa.Column("entry_method", _ENTRY_METHOD, nullable=False, server_default="manual"),
        sa.Column("recorded_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("target_label", sa.String(255), nullable=False),
        sa.Column("before_value", sa.Text, nullable=True),
        sa.Column("after_value", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    # Seed the fixed role set. Users can't exist without a valid role_id,
    # so this has to land in the same migration that creates both tables.
    roles_table = sa.table(
        "roles",
        sa.column("code", sa.String),
        sa.column("display_name", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "code": "admin",
                "display_name": "管理员",
                "description": "录入、审核、用户与配置管理",
            },
            {
                "code": "operator",
                "display_name": "操作员",
                "description": "运行录入，无审核权限",
            },
            {
                "code": "reviewer",
                "display_name": "复核员",
                "description": "仅查看与导出，无录入权限",
            },
        ],
    )


def downgrade() -> None:
    """Remove the initial production schema in reverse dependency order."""
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("measurements")
    op.drop_index("ix_runs_run_code", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_materials_material_no", table_name="materials")
    op.drop_table("materials")
    op.drop_index("ix_users_account", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_roles_code", table_name="roles")
    op.drop_table("roles")
    # MySQL drops each column's inline ENUM with its table automatically;
    # explicitly dropping the sa.Enum types here would only matter for a
    # dialect (e.g. Postgres) with standalone named enum types.

"""Independent current display rounding; no production values are rewritten.

Revision ID: c2a54f8d7109
Revises: b6d84e19a203
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "c2a54f8d7109"
down_revision = "b6d84e19a203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Seed presentation from the current factory precision, then allow independent changes."""
    groups = ("resistance", "thickness", "speed", "length", "result")
    op.create_table(
        "display_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        *(
            sa.Column(
                f"{name}_places",
                sa.Integer,
                nullable=False,
                server_default="3" if name == "thickness" else "2",
            )
            for name in groups
        ),
        sa.Column("rounding", sa.String(16), nullable=False, server_default="half_up"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column("updated_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_display_settings_singleton"),
        sa.CheckConstraint("revision > 0", name="ck_display_settings_revision"),
        *(
            sa.CheckConstraint(f"{name}_places BETWEEN 0 AND 6", name=f"ck_display_{name}")
            for name in groups
        ),
        sa.CheckConstraint("rounding IN ('half_up', 'half_even')", name="ck_display_rounding"),
    )
    names = ", ".join(f"{name}_places" for name in groups)
    source = ", ".join(f"a.{name}_places" for name in groups)
    op.get_bind().execute(
        sa.text(
            f"INSERT INTO display_settings (id, {names}, rounding, updated_at) "
            f"SELECT 1, {source}, a.rounding, :now FROM production_settings s "
            "JOIN accuracy_versions a ON a.id = s.accuracy_version_id WHERE s.id = 1"
        ).bindparams(
            sa.bindparam("now", value=datetime.now(UTC).replace(tzinfo=None), type_=sa.DateTime())
        ),
    )


def downgrade() -> None:
    """Remove display preferences only; production data and run policies remain intact."""
    op.drop_table("display_settings")

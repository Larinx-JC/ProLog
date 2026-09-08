"""Persistent sessions, single-use grants, and shared authentication coordination.

Revision ID: 7a9b31c4d502
Revises: 0c3dff882627
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "7a9b31c4d502"
down_revision = "0c3dff882627"
branch_labels = None
depends_on = None

_TIME = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    """Preserve existing users while adding server-side authentication persistence."""
    op.add_column("users", sa.Column("activated_at", _TIME, nullable=True))
    op.execute("UPDATE users SET activated_at = created_at")
    op.create_table(
        "auth_state",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("bootstrap_completed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.CheckConstraint("id = 1", name="ck_auth_state_singleton"),
    )
    op.execute("INSERT INTO auth_state (id, bootstrap_completed) VALUES (1, 0)")
    op.execute(
        "UPDATE auth_state SET bootstrap_completed = 1 WHERE EXISTS "
        "(SELECT 1 FROM users JOIN roles ON roles.id = users.role_id WHERE roles.code = 'admin')"
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
        sa.Column("last_activity_at", _TIME, nullable=False),
        sa.Column("expires_at", _TIME, nullable=False),
        sa.Column("revoked_at", _TIME, nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_login_sessions_expiry"),
        sa.CheckConstraint("last_activity_at >= created_at", name="ck_login_sessions_activity"),
    )
    op.create_index(
        "ix_login_sessions_token_digest", "login_sessions", ["token_digest"], unique=True
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_index("ix_login_sessions_expires_at", "login_sessions", ["expires_at"])
    op.create_table(
        "access_grants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issued_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
        sa.Column("expires_at", _TIME, nullable=False),
        sa.Column("consumed_at", _TIME, nullable=True),
        sa.Column("revoked_at", _TIME, nullable=True),
        sa.CheckConstraint(
            "purpose IN ('activation', 'recovery')", name="ck_access_grants_purpose"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_access_grants_expiry"),
    )
    op.create_index("ix_access_grants_token_digest", "access_grants", ["token_digest"], unique=True)
    op.create_index("ix_access_grants_user_id", "access_grants", ["user_id"])
    op.create_index("ix_access_grants_expires_at", "access_grants", ["expires_at"])
    op.create_table(
        "auth_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("expires_at", _TIME, nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_auth_throttles_attempts"),
    )
    op.create_index("ix_auth_throttles_expires_at", "auth_throttles", ["expires_at"])


def downgrade() -> None:
    """Discard authentication credentials while retaining all pre-existing user rows."""
    op.drop_table("auth_throttles")
    op.drop_table("access_grants")
    op.drop_table("login_sessions")
    op.drop_table("auth_state")
    op.drop_column("users", "activated_at")

"""Verify the initial migration's seeded reference data landed correctly.

Run after `alembic upgrade head` against a real (migrated) database --
this isn't a pytest test on its own because it needs actual migrated
data, not the fast SQLite-in-memory fixture the rest of the suite uses
(see tests/test_models.py's module docstring). test_role_seed_values_
are_distinct in that file only proves Role *can* hold three distinct
rows; it never touches the migration's own seed data, so a typo'd or
dropped `op.bulk_insert` there would go uncaught. This is what actually
checks the migration's output, wired into CI as a plain script step
between `alembic upgrade head` and `alembic downgrade base`.

fetch_seeded_roles/find_mismatch are split out from main() specifically
so they're unit-testable (see tests/test_verify_seed_data.py) without
needing a real database for the comparison logic itself.
"""

import sys

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings

# code -> {display_name, description}, exactly as seeded by
# alembic/versions/0c3dff882627_initial_schema.py's op.bulk_insert.
EXPECTED_ROLES = {
    "admin": {"display_name": "管理员", "description": "录入、审核、用户与配置管理"},
    "operator": {"display_name": "操作员", "description": "运行录入，无审核权限"},
    "reviewer": {"display_name": "复核员", "description": "仅查看与导出，无录入权限"},
}


def fetch_seeded_roles(engine: Engine) -> dict[str, dict[str, str]]:
    """Query the roles table, shaped to match EXPECTED_ROLES exactly."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT code, display_name, description FROM roles ORDER BY code")
        ).fetchall()
    return {code: {"display_name": dn, "description": desc} for code, dn, desc in rows}


def find_mismatch(
    actual: dict[str, dict[str, str]], expected: dict[str, dict[str, str]]
) -> str | None:
    """Return a human-readable description of the mismatch, or None if
    `actual` matches `expected` exactly."""
    if actual != expected:
        return f"Seeded roles mismatch.\nExpected: {expected}\nActual:   {actual}"
    return None


def main() -> None:
    engine = create_engine(get_settings().database_url)
    actual = fetch_seeded_roles(engine)
    mismatch = find_mismatch(actual, EXPECTED_ROLES)
    if mismatch:
        print(mismatch)
        sys.exit(1)
    print(f"OK: seeded roles match exactly -- {actual}")


if __name__ == "__main__":
    main()

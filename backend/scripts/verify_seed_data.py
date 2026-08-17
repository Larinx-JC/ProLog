"""Verify the initial migration's seeded reference data landed correctly.

Run after `alembic upgrade head` against a real (migrated) database --
this isn't a pytest test because it needs actual migrated data, not the
fast SQLite-in-memory fixture the rest of the suite uses (see
tests/test_models.py's module docstring). test_role_seed_values_are_
distinct in that file only proves Role *can* hold three distinct rows;
it never touches the migration's own seed data, so a typo'd or dropped
`op.bulk_insert` there would go uncaught. This script is what actually
checks the migration's output, wired into CI as a plain script step
between `alembic upgrade head` and `alembic downgrade base`.
"""

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

EXPECTED_ROLES = {
    "admin": "管理员",
    "operator": "操作员",
    "reviewer": "复核员",
}


def main() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT code, display_name FROM roles ORDER BY code")).fetchall()

    actual = {code: display_name for code, display_name in rows}
    if actual != EXPECTED_ROLES:
        print(f"Seeded roles mismatch.\nExpected: {EXPECTED_ROLES}\nActual:   {actual}")
        sys.exit(1)
    print(f"OK: seeded roles match exactly -- {actual}")


if __name__ == "__main__":
    main()

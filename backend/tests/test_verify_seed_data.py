"""Unit tests for scripts/verify_seed_data.py.

This script is the only thing that actually checks the initial
migration's seeded role data (see its own docstring) -- it needs its
own tests same as any other important function, not just a CI run that
only ever exercises the successful path.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Role
from scripts.verify_seed_data import EXPECTED_ROLES, fetch_seeded_roles, find_mismatch, main


def test_find_mismatch_returns_none_when_matching() -> None:
    """Identical dicts must report no mismatch."""
    assert find_mismatch(EXPECTED_ROLES, EXPECTED_ROLES) is None


def test_find_mismatch_reports_wrong_display_name() -> None:
    """A wrong display_name (e.g. a typo in the migration's seed data)
    must be caught, not just a missing/extra role."""
    corrupted = {
        **EXPECTED_ROLES,
        "admin": {**EXPECTED_ROLES["admin"], "display_name": "WRONG"},
    }
    message = find_mismatch(corrupted, EXPECTED_ROLES)
    assert message is not None
    assert "WRONG" in message


def test_find_mismatch_reports_wrong_description() -> None:
    """A wrong description must be caught too -- not just code/display_name."""
    corrupted = {
        **EXPECTED_ROLES,
        "operator": {**EXPECTED_ROLES["operator"], "description": "WRONG"},
    }
    message = find_mismatch(corrupted, EXPECTED_ROLES)
    assert message is not None
    assert "WRONG" in message


def test_find_mismatch_reports_missing_role() -> None:
    """A role missing entirely (e.g. a dropped bulk_insert row) must be caught."""
    missing_reviewer = {k: v for k, v in EXPECTED_ROLES.items() if k != "reviewer"}
    assert find_mismatch(missing_reviewer, EXPECTED_ROLES) is not None


def test_fetch_seeded_roles_reads_exact_shape_from_the_database(db_session: Session) -> None:
    """fetch_seeded_roles must read real rows into the same
    {code: {display_name, description}} shape find_mismatch compares
    against -- seeded here with EXPECTED_ROLES' own values, so this also
    doubles as an end-to-end check that a correctly-seeded database
    passes verification."""
    for code, fields in EXPECTED_ROLES.items():
        db_session.add(Role(code=code, **fields))
    db_session.commit()

    engine = db_session.get_bind()
    actual = fetch_seeded_roles(engine)

    assert actual == EXPECTED_ROLES
    assert find_mismatch(actual, EXPECTED_ROLES) is None


def _seed_sqlite_roles_table(db_path: Path, roles: dict[str, dict[str, str]]) -> None:
    """A minimal roles table at db_path, seeded with `roles` -- enough
    for main()'s raw SQL SELECT, without needing the full ORM schema or
    a real Alembic migration."""
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE roles (code TEXT, display_name TEXT, description TEXT)")
        )
        for code, fields in roles.items():
            conn.execute(
                text(
                    "INSERT INTO roles (code, display_name, description) "
                    "VALUES (:code, :display_name, :description)"
                ),
                {"code": code, **fields},
            )
    engine.dispose()


def test_main_succeeds_against_correctly_seeded_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() end-to-end, against a real (temp file) SQLite database --
    not the fast in-memory fixture -- standing in for what CI actually
    runs against MySQL. Must complete without raising/exiting."""
    db_path = tmp_path / "seed_ok.db"
    _seed_sqlite_roles_table(db_path, EXPECTED_ROLES)
    monkeypatch.setattr(
        "scripts.verify_seed_data.get_settings",
        lambda: SimpleNamespace(database_url=f"sqlite:///{db_path.as_posix()}"),
    )

    main()

    assert "OK" in capsys.readouterr().out


def test_main_exits_nonzero_against_corrupted_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() must fail loudly (non-zero exit) when the seeded data is
    wrong -- this is what makes it useful as a CI gate rather than a
    script nobody would notice silently passing on bad data."""
    db_path = tmp_path / "seed_bad.db"
    corrupted = {
        **EXPECTED_ROLES,
        "admin": {**EXPECTED_ROLES["admin"], "display_name": "WRONG"},
    }
    _seed_sqlite_roles_table(db_path, corrupted)
    monkeypatch.setattr(
        "scripts.verify_seed_data.get_settings",
        lambda: SimpleNamespace(database_url=f"sqlite:///{db_path.as_posix()}"),
    )

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

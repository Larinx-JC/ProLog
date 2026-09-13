"""MySQL display persistence, migration constraints and serialized preference updates."""

from dataclasses import replace

import pytest
from alembic.config import Config
from sqlalchemy import func, select

from app.domain.numeric import AccuracyPolicy
from app.models import AuditLog
from app.services.auth import AuthService
from app.services.production.display_settings import DisplaySettingsService
from tests.mysql.test_production_mysql import race
from tests.production_fixtures import build_case, request_id
from tests.test_display_migration import assert_display_migration
from tests.test_display_settings import assert_display_preserves_history

pytestmark = pytest.mark.mysql


def test_mysql_display_preserves_reviewed_history(mysql_auth: AuthService) -> None:
    """Read rounded existing final data on MySQL while all original values and alarms stay exact."""
    assert_display_preserves_history(mysql_auth, "reviewed")


def test_mysql_display_update_conflict_and_coherent_read(mysql_auth: AuthService) -> None:
    """Commit one settings revision; readers must see a whole old or new preference set."""
    case = build_case(mysql_auth)
    service = DisplaySettingsService(mysql_auth)
    run = case.start()
    case.sample(run)
    preference = replace(
        AccuracyPolicy(), resistance_places=0, thickness_places=6, rounding="half_even"
    )

    def update():
        """Submit an independent Admin request against the same optimistic revision."""
        return service.update(case.admin.token, request_id(), 1, preference, "Update screen")

    results = race(update, update, lambda: case.runs.get_run(case.admin.token, run.id))
    assert results[:2].count("revision_conflict") == 1
    shown = results[2].as_dict()
    fields = shown["display"]["settings"]["precision"]
    measurement = shown["measurements"][0]["display"]
    assert (
        fields["resistance_places"],
        fields["thickness_places"],
        measurement["point_1"],
        measurement["thickness"],
    ) in {
        (2, 3, "100.00", "0.007"),
        (0, 6, "100", "0.007000"),
    }
    with mysql_auth.factory() as db:
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.action == "display_settings_changed")
            )
            == 1
        )


def test_mysql_display_migration_preserves_production(mysql_auth: AuthService) -> None:
    """Verify MySQL display seeds, constraints, drift and populated downgrade preservation."""
    assert_display_migration(Config("alembic.ini"), mysql_auth.factory.kw["bind"])

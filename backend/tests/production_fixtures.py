"""Synthetic production setup shared by unit, migration and MySQL behavior tests."""

from dataclasses import asdict, dataclass
from uuid import uuid4

from app.domain.numeric import AccuracyPolicy
from app.models import AccuracyVersion, DisplaySettings, ProductionSettings
from app.services.auth import AuthService
from app.services.auth_types import SessionIssued
from app.services.production.base import Document
from app.services.production.materials import MaterialService
from app.services.production.measurements import MeasurementService
from app.services.production.reviews import ReviewService
from app.services.production.runs import RunService
from app.services.production.settings import AccuracySettingsService
from tests.auth_fixtures import bootstrap_login

MATERIAL_RULES = dict(
    standard_value="100.00",
    upper_limit="110.00",
    lower_limit="90.00",
    thickness_min="0.006",
    thickness_max="0.008",
)
SAMPLE = dict(
    point_1="100.00",
    point_2="100.00",
    point_3="100.00",
    point_4="100.00",
    thickness="0.007",
    meter_count="1.00",
)


def request_id() -> str:
    """Generate an independent synthetic client request identity."""
    return str(uuid4())


def seed_settings(auth: AuthService) -> None:
    """Mirror migration defaults only for create_all unit fixtures; never seed real tests twice."""
    with auth.factory.begin() as db:
        if db.get(DisplaySettings, 1) is None:
            db.add(DisplaySettings(id=1, updated_at=auth.clock.now()))
        if db.get(ProductionSettings, 1) is None:
            db.add(
                AccuracyVersion(
                    id=2,
                    **asdict(AccuracyPolicy()),
                    calculation_version="target_v1",
                    created_at=auth.clock.now(),
                    created_by_id=None,
                )
            )
            db.flush()
            db.add(ProductionSettings(id=1, accuracy_version_id=2))


@dataclass
class ProductionCase:
    """Actual service composition with synthetic accounts and controlled time."""

    auth: AuthService
    admin: SessionIssued
    material: Document
    runs: RunService
    measurements: MeasurementService
    materials: MaterialService
    settings: AccuracySettingsService
    reviews: ReviewService

    def start(self, actor: SessionIssued | None = None) -> Document:
        """Start a real service run with a sixty-second sampling interval."""
        return self.runs.start(
            (actor or self.admin).token, request_id(), self.material.id, "B-TEST", 60
        )

    def sample(self, run: Document, actor: SessionIssued | None = None, **changes) -> Document:
        """Record slot zero with exact synthetic values using the run's returned revision."""
        return self.measurements.save(
            (actor or self.admin).token,
            request_id(),
            run.id,
            run.revision,
            run.as_dict()["start_time"],
            dict(SAMPLE, **changes),
            slot_index=0,
        )


def build_case(auth: AuthService) -> ProductionCase:
    """Create real persisted material/auth setup usable on either disposable database dialect."""
    seed_settings(auth)
    admin = bootstrap_login(auth)
    materials = MaterialService(auth)
    material = materials.create(admin.token, request_id(), "M-PRODUCTION", MATERIAL_RULES)
    return ProductionCase(
        auth,
        admin,
        material,
        RunService(auth),
        MeasurementService(auth),
        materials,
        AccuracySettingsService(auth),
        ReviewService(auth),
    )

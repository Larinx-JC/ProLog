"""Production HTTP routes delegate writes to the approved service transaction boundaries."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api import production_schemas as schema
from app.api.auth import check_csrf, service, session_token
from app.domain.numeric import AccuracyPolicy
from app.services.production.display_settings import DisplaySettingsService
from app.services.production.materials import MaterialService
from app.services.production.measurements import MeasurementService
from app.services.production.reads import ProductionReadService
from app.services.production.reviews import ReviewService
from app.services.production.runs import RunService
from app.services.production.settings import AccuracySettingsService

router = APIRouter(prefix="/production", tags=["production"])
Identifier = Annotated[int, Path(ge=1, le=schema.MAX_INTEGER)]
Offset = Annotated[int, Query(ge=0, le=schema.MAX_INTEGER)]
Limit = Annotated[int, Query(ge=1, le=200)]
WRITES = [Depends(check_csrf)]


def reads(request: Request) -> ProductionReadService:
    """Compose reads from the app's injectable authentication/session/clock dependencies."""
    return ProductionReadService(service(request))


@router.get("/runs", response_model=schema.Page[schema.RunReadOut])
def list_runs(request: Request, offset: Offset = 0, limit: Limit = 50) -> dict:
    """Return a newest-first page of run metadata without embedded sample collections."""
    return reads(request).runs(session_token(request), offset, limit).as_dict()


@router.post("/runs", dependencies=WRITES, response_model=schema.RunOut, status_code=201)
def start_run(body: schema.StartInput, request: Request) -> dict:
    """Start production with a server-owned timestamp and immutable captured rules."""
    return RunService(service(request)).start(session_token(request), **body.model_dump()).as_dict()


@router.get("/runs/{identifier}", response_model=schema.RunDetailOut)
def get_run(identifier: Identifier, request: Request) -> dict:
    """Return bounded detail; clients page samples through the measurement endpoint."""
    return reads(request).run(session_token(request), identifier).as_dict()


@router.get("/runs/{identifier}/measurements", response_model=schema.MeasurementPage)
def list_measurements(
    identifier: Identifier, request: Request, offset: Offset = 0, limit: Limit = 50
) -> dict:
    """Read one parent's sample page with its current run and display-policy revisions."""
    return reads(request).measurements(session_token(request), identifier, offset, limit).as_dict()


@router.post(
    "/runs/{identifier}/measurements",
    dependencies=WRITES,
    response_model=schema.SampleReceipt,
    status_code=201,
)
def record_measurement(identifier: Identifier, body: schema.SampleInput, request: Request) -> dict:
    """Record partial or complete data; missing/abnormal status is decided by the service."""
    return (
        MeasurementService(service(request))
        .save(session_token(request), run_id=identifier, **body.model_dump())
        .as_dict()
    )


@router.put(
    "/runs/{identifier}/measurements/{measurement_id}",
    dependencies=WRITES,
    response_model=schema.SampleReceipt,
)
def correct_measurement(
    identifier: Identifier,
    measurement_id: Identifier,
    body: schema.CorrectionInput,
    request: Request,
) -> dict:
    """Replace an existing sample using both revisions and an audited correction reason."""
    return (
        MeasurementService(service(request))
        .save(
            session_token(request),
            run_id=identifier,
            measurement_id=measurement_id,
            **body.model_dump(),
        )
        .as_dict()
    )


@router.get("/runs/{identifier}/schedule", response_model=schema.ScheduleOut)
def get_schedule(
    identifier: Identifier, request: Request, offset: Offset = 0, limit: Limit = 50
) -> dict:
    """Read real and virtual scheduled samples without renewing session activity."""
    return (
        RunService(service(request))
        .schedule(session_token(request), identifier, offset, limit)
        .as_dict()
    )


@router.post("/runs/{identifier}/close", dependencies=WRITES, response_model=schema.RunOut)
def close_run(identifier: Identifier, body: schema.CloseInput, request: Request) -> dict:
    """Submit eligible production for review, with Admin-only missing-data exceptions."""
    return (
        RunService(service(request))
        .close(session_token(request), identifier=identifier, **body.model_dump())
        .as_dict()
    )


@router.post("/runs/{identifier}/review", dependencies=WRITES, response_model=schema.ReviewOut)
def review_run(identifier: Identifier, body: schema.ReviewInput, request: Request) -> dict:
    """Record a final reasoned Admin decision through the single review writer."""
    return (
        ReviewService(service(request))
        .review(session_token(request), identifier=identifier, **body.model_dump())
        .as_dict()
    )


@router.get("/materials", response_model=schema.Page[schema.MaterialReadOut])
def list_materials(request: Request, offset: Offset = 0, limit: Limit = 50) -> dict:
    """List standards including inactive history; clients cannot silently reinterpret old rules."""
    return reads(request).materials(session_token(request), offset, limit).as_dict()


@router.get("/materials/{identifier}", response_model=schema.MaterialReadOut)
def get_material(identifier: Identifier, request: Request) -> dict:
    """Expose exact rules and current rounded copies through the common read serializer."""
    return reads(request).material(session_token(request), identifier).as_dict()


@router.post("/materials", dependencies=WRITES, response_model=schema.MaterialOut, status_code=201)
def create_material(body: schema.MaterialCreateInput, request: Request) -> dict:
    """Create an Admin-maintained standard without accepting calculated or identity fields."""
    return (
        MaterialService(service(request))
        .create(session_token(request), body.request_id, body.material_no, body.rules.model_dump())
        .as_dict()
    )


@router.put("/materials/{identifier}", dependencies=WRITES, response_model=schema.MaterialOut)
def update_material(
    identifier: Identifier, body: schema.MaterialUpdateInput, request: Request
) -> dict:
    """Replace material rules/state atomically; existing run snapshots cannot change."""
    return (
        MaterialService(service(request))
        .update(
            session_token(request),
            body.request_id,
            identifier,
            body.expected_revision,
            body.rules.model_dump(),
            body.is_active,
            body.reason,
        )
        .as_dict()
    )


@router.get("/settings/accuracy", response_model=schema.AccuracyOut)
def get_accuracy(request: Request) -> dict:
    """Return recording and operational settings to the currently authenticated Admin."""
    return AccuracySettingsService(service(request)).get(session_token(request)).as_dict()


@router.put("/settings/accuracy", dependencies=WRITES, response_model=schema.AccuracyOut)
def update_accuracy(body: schema.AccuracyUpdateInput, request: Request) -> dict:
    """Publish a complete recording policy and current Operator abnormal-run authority."""
    return (
        AccuracySettingsService(service(request))
        .update(
            session_token(request),
            body.request_id,
            body.expected_revision,
            AccuracyPolicy(**body.accuracy.model_dump()),
            body.operator_abnormal_allowed,
            body.reason,
        )
        .as_dict()
    )


@router.get("/settings/display", response_model=schema.DisplaySettingsOut)
def get_display(request: Request) -> dict:
    """Let permitted readers obtain current display preferences without extending idle time."""
    return DisplaySettingsService(service(request)).get(session_token(request)).as_dict()


@router.put("/settings/display", dependencies=WRITES, response_model=schema.DisplaySettingsOut)
def update_display(body: schema.DisplayUpdateInput, request: Request) -> dict:
    """Change presentation independently of persisted quantities and captured run policy."""
    return (
        DisplaySettingsService(service(request))
        .update(
            session_token(request),
            body.request_id,
            body.expected_revision,
            AccuracyPolicy(**body.precision.model_dump()),
            body.reason,
        )
        .as_dict()
    )


@router.get("/audit-logs", response_model=schema.Page[schema.AuditOut])
def list_audits(request: Request, offset: Offset = 0, limit: Limit = 50) -> dict:
    """Permit Admin/Reviewer audit inspection; Operators cannot bypass the service check."""
    return reads(request).audits(session_token(request), offset, limit).as_dict()


@router.get("/overview", response_model=schema.OverviewOut)
def overview(request: Request) -> dict:
    """Expose explicit status/day counts and five recent run summaries."""
    return reads(request).overview(session_token(request)).as_dict()

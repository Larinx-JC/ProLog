"""Explicit production request and response contracts; decimal quantities stay strings."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EntryMethod, MeasurementStatus, ReviewResolution, RunStatus

MAX_INTEGER = 2147483647
Positive = Annotated[int, Field(strict=True, ge=1, le=MAX_INTEGER)]
DecimalText = Annotated[str, Field(max_length=32, pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")]
Reason = Annotated[str, Field(min_length=1, max_length=4000)]
RequestId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")]
Places = Annotated[int, Field(strict=True, ge=0, le=6)]


class Body(BaseModel):
    """Reject coercion and extra fields at the public write boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Precision(Body):
    """A complete per-quantity policy; PUT never silently resets omitted settings."""

    resistance_places: Places
    thickness_places: Places
    speed_places: Places
    length_places: Places
    result_places: Places
    rounding: Literal["half_up", "half_even"]


class RulesInput(Body):
    """Exact material rules with the agreed initial two-percent deviation tolerance."""

    standard_value: DecimalText
    upper_limit: DecimalText
    lower_limit: DecimalText
    thickness_min: DecimalText
    thickness_max: DecimalText
    deviation_pct_threshold: DecimalText = "2"
    deviation_check_enabled: bool = True
    thickness_check_enabled: bool = True
    limits_check_enabled: bool = True


class ReadingInput(Body):
    """A complete replacement reading set; omitted optional fields are genuinely missing."""

    point_1: DecimalText | None = None
    point_2: DecimalText | None = None
    point_3: DecimalText | None = None
    point_4: DecimalText | None = None
    thickness: DecimalText | None = None
    meter_count: DecimalText | None = None
    speed: DecimalText | None = None


class StartInput(Body):
    """Create a run using server time and the current active material's captured rules."""

    request_id: RequestId
    material_id: Positive
    raw_material_batch: Annotated[str, Field(min_length=1, max_length=100)]
    interval_seconds: Positive


class SampleInput(Body):
    """Record a scheduled or extra sample against an optimistic run revision."""

    request_id: RequestId
    expected_run_revision: Positive
    measurement_time: Annotated[str, Field(min_length=19, max_length=40)]
    values: ReadingInput
    slot_index: Annotated[int, Field(ge=0, le=MAX_INTEGER)] | None = None
    reason: Reason | None = None


class CorrectionInput(SampleInput):
    """Correct an existing sample with its own revision and an explicit explanation."""

    expected_revision: Positive
    reason: Reason


class CloseInput(Body):
    """Submit a run for review; the service enforces the Admin-only missing-data exception."""

    request_id: RequestId
    expected_revision: Positive
    exception_reason: Reason | None = None


class ReviewInput(Body):
    """Record a final Admin decision, with its permitted source checked by the service."""

    request_id: RequestId
    expected_revision: Positive
    resolution: Literal["approved", "confirmed_abnormal", "false_alarm"]
    reason: Reason


class MaterialCreateInput(Body):
    """Create one named material with complete validated rules."""

    request_id: RequestId
    material_no: Annotated[str, Field(min_length=1, max_length=50)]
    rules: RulesInput


class MaterialUpdateInput(Body):
    """Replace rules and activation state without renaming the material or changing old runs."""

    request_id: RequestId
    expected_revision: Positive
    rules: RulesInput
    is_active: bool
    reason: Reason


class AccuracyUpdateInput(Body):
    """Publish a recording policy and current Operator authority together."""

    request_id: RequestId
    expected_revision: Positive
    accuracy: Precision
    operator_abnormal_allowed: bool
    reason: Reason


class DisplayUpdateInput(Body):
    """Change presentation alone for all current screens."""

    request_id: RequestId
    expected_revision: Positive
    precision: Precision
    reason: Reason


class PublicModel(BaseModel):
    """Explicit detached response fields reject accidental undeclared data disclosure."""

    model_config = ConfigDict(extra="forbid")


class DisplaySettingsOut(PublicModel):
    """One current presentation revision, shared by a whole response."""

    id: int
    revision: int
    precision: Precision
    updated_at: str
    updated_by_id: int | None


class AccuracyOut(PublicModel):
    """Current recording defaults and immediate abnormal-run permission switch."""

    id: int
    revision: int
    accuracy_version_id: int
    operator_abnormal_allowed: bool
    accuracy: Precision


class RunOut(PublicModel):
    """Canonical run history, suitable for stable mutation receipts."""

    id: int
    revision: int
    run_code: str
    material_id: int
    raw_material_batch: str
    created_by_id: int
    status: RunStatus
    start_time: str
    end_time: str | None
    interval_seconds: int
    accuracy_version_id: int
    accuracy: Precision
    calculation_version: str
    rules: RulesInput
    pending_from: Literal["active", "abnormal"] | None
    review_resolution: ReviewResolution | None
    review_reason: str | None
    reviewed_by_id: int | None
    reviewed_at: str | None
    missing_count_at_close: int | None
    closure_exception_reason: str | None


class RunDisplay(PublicModel):
    """Rounded rule copies and the current policy that produced them."""

    settings: DisplaySettingsOut
    rules: dict[str, str | None]


class RunReadOut(RunOut):
    """A bounded run record; samples are obtained from their separate paginated endpoint."""

    display: RunDisplay


class RunDetailOut(RunReadOut):
    """Run metadata with aggregate completeness, without a nested sample collection."""

    missing_count: int | None
    measurement_count: int


class ReviewOut(RunOut):
    """A review receipt exposes whether the Admin reviewed their own recorded work."""

    self_review: bool


class MeasurementOut(PublicModel):
    """Canonical persisted readings and calculations retain their captured decimal scale."""

    id: int
    revision: int
    run_id: int
    slot_index: int | None
    measurement_time: str
    recorded_at: str | None
    recorded_by_id: int | None
    status: MeasurementStatus
    alarm_codes: list[str]
    entry_method: EntryMethod
    point_1: str | None
    point_2: str | None
    point_3: str | None
    point_4: str | None
    thickness: str | None
    meter_count: str | None
    speed: str | None
    average_value: str | None
    max_deviation: str | None
    deviation_percent: str | None
    target_deviation: str | None
    target_deviation_percent: str | None


class MeasurementReadOut(MeasurementOut):
    """Presentation values are additional copies, never substitutes for editable readings."""

    display: dict[str, str | None]


class SampleReceipt(MeasurementOut):
    """A mutation receipt contains the resulting run revision for the next write."""

    run_revision: int
    run_status: RunStatus
    missing_fields: list[str]


class MaterialOut(PublicModel):
    """Named material metadata with exact, explicitly serialized detection rules."""

    id: int
    revision: int
    material_no: str
    is_active: bool
    rules: RulesInput


class MaterialReadOut(MaterialOut):
    """Current material rules retain old exact precision even while inactive."""

    display: RunDisplay


class Page[T](PublicModel):
    """A bounded collection with stable ordering and an explicit continuation indicator."""

    items: list[T]
    offset: int
    limit: int
    total: int
    has_more: bool


class MeasurementPage(Page[MeasurementReadOut]):
    """Capture parent revision and both policies consistently with this measurement page."""

    run_id: int
    run_revision: int
    accuracy: Precision
    calculation_version: str
    display_settings: DisplaySettingsOut


class SlotOut(PublicModel):
    """A real or virtual scheduled sample position."""

    index: int
    due_time: str
    measurement_id: int | None
    status: MeasurementStatus


class ScheduleOut(PublicModel):
    """Existing bounded schedule contract, including virtual missing positions."""

    id: int
    revision: int
    expected_count: int
    missing_count: int
    offset: int
    slots: list[SlotOut]


class AuditOut(PublicModel):
    """Original audit payload text is retained; it is never reformatted or rewritten."""

    id: int
    occurred_at: str
    action: str
    actor_id: int | None
    target_type: str
    target_id: int | None
    target_label: str
    before_value: str | None
    after_value: str | None
    reason: str | None


class OverviewOut(PublicModel):
    """Explicit all-time status counts and factory-day run starts avoid ambiguous KPI rates."""

    as_of: str
    factory_timezone: str
    factory_date: str
    today_started_runs: int
    total_runs: int
    status_counts: dict[RunStatus, int]
    recent_runs: list[RunReadOut]

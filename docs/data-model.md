# Data Model (Section 2)

## Entity-relationship diagram

```mermaid
erDiagram
    ROLE ||--o{ USER : "has"
    USER ||--o{ RUN : "creates"
    USER ||--o{ RUN : "reviews (nullable)"
    USER ||--o{ MEASUREMENT : "records (nullable)"
    USER ||--o{ AUDIT_LOG : "acts as (nullable)"
    MATERIAL ||--o{ RUN : "detected against"
    RUN ||--o{ MEASUREMENT : "contains"

    ROLE {
        int id PK
        string code UK "admin / operator / reviewer"
        string display_name
        string description
    }
    USER {
        int id PK
        string name
        string account UK
        string password_hash
        string position
        int role_id FK
        bool is_active
        bool must_change_password
        datetime created_at
        datetime updated_at
    }
    MATERIAL {
        int id PK
        string material_no UK
        decimal standard_value "current default for new runs"
        decimal upper_limit
        decimal lower_limit
        decimal thickness_min
        decimal thickness_max
        bool deviation_check_enabled
        decimal deviation_pct_threshold
        bool thickness_check_enabled
        bool limits_check_enabled
        bool is_active "soft delete"
        datetime created_at
        datetime updated_at
    }
    RUN {
        int id PK
        string run_code UK
        int material_id FK
        decimal standard_value "snapshotted at creation"
        string raw_material_batch
        int interval_seconds
        enum status "active/abnormal/pending_review/reviewed"
        enum pending_from "nullable: active or abnormal"
        datetime start_time
        datetime end_time "nullable"
        int created_by_id FK
        enum review_resolution "nullable"
        text review_reason "nullable"
        int reviewed_by_id FK "nullable"
        datetime reviewed_at "nullable"
        datetime created_at
        datetime updated_at
    }
    MEASUREMENT {
        int id PK
        int run_id FK
        datetime measurement_time
        decimal meter_count "nullable"
        decimal speed "nullable"
        decimal point_1 "nullable"
        decimal point_2 "nullable"
        decimal point_3 "nullable"
        decimal point_4 "nullable"
        decimal thickness "nullable"
        decimal average_value "nullable, computed"
        decimal max_deviation "nullable, computed"
        decimal deviation_percent "nullable, computed"
        enum status "missing/completed/abnormal"
        enum entry_method "manual/automated"
        int recorded_by_id FK "nullable"
        datetime recorded_at "nullable"
    }
    AUDIT_LOG {
        int id PK
        datetime occurred_at
        int actor_id FK "nullable"
        string target_type "e.g. run, material, user"
        int target_id "nullable, no FK (polymorphic)"
        string target_label
        text before_value "nullable"
        text after_value "nullable"
        text reason "nullable"
    }
```

## Run state machine

```mermaid
stateDiagram-v2
    [*] --> Active: submitStartRun
    Active --> Abnormal: measurement flagged abnormal
    Active --> PendingReview: close (pending_from=Active)
    Abnormal --> PendingReview: close (pending_from=Abnormal)
    PendingReview --> Reviewed: review + resolution + reason
    Reviewed --> [*]
```

There is no "closed without review" path — every run reaches its
terminal state (`Reviewed`) through review. `review_resolution` is
`approved` when `pending_from=active`, or the reviewer's choice of
`confirmed_abnormal` / `false_alarm` when `pending_from=abnormal`.

## Design decisions and why

- **Role is a normalized table**, not an enum column on User. Only 3 rows
  exist today (seeded by the initial migration), but a future role (or
  per-role metadata) becomes a data change instead of a schema migration.
- **No separate ReviewRecord table.** Review outcome lives directly on
  Run (`review_resolution`, `review_reason`, `reviewed_by_id`,
  `reviewed_at`) — one decision per run, matching the actual workflow.
  There's no reopen/re-review history; `Reviewed` is terminal.
- **Run snapshots `standard_value` from Material at creation time.** This
  is what makes a separate material-standard-version-history table
  unnecessary: an existing run's measurements are always judged against
  *its own* snapshotted value, never a live lookup, so a later change to
  a material's current standard can never retroactively change how a
  past run's data reads. Changes to a material's standard are still
  visible via AuditLog (before/after free text), matching how material
  standard changes were already shown in the original design.
- **All numeric columns are `DECIMAL(10, 2)`**, mapped to Python
  `Decimal` (never `float`), applied uniformly across every numeric
  field rather than case-by-case — see `CONTRIBUTING.md`.
- **`Measurement.entry_method`** (manual/automated, default manual) is
  the one column added now in anticipation of the Section 8 ingestion
  portal — deliberately minimal (a single column) rather than a fuller
  speculative field set, since Section 8 itself isn't scoped yet.
- **`AuditLog.target_id` has no FK constraint** — it's polymorphic
  (points at a run, material, or user row depending on `target_type`),
  and before/after are free text rather than structured per-field diffs,
  matching the original design's simple audit trail.

## Migration

`backend/alembic/versions/0c3dff882627_initial_schema.py` — hand-written
(no local MySQL was available for `alembic revision --autogenerate`),
verified locally against SQLite (upgrade/downgrade round-trip, UTF-8
role names) and against real MySQL 8.4 via CI's Alembic smoke test.
Enum values are inlined as literals in the migration rather than
imported from `app.models.enums`, since migrations are a frozen
historical record and should not silently drift if an enum changes in a
later migration.

# Archived planning and review notes

Archived on 2026-09-07 from the former project outline.

These notes preserve the development history through Section 2. They are not
the current requirements or evidence of owner approval. Some statements were
later corrected, including the claim that `pending_from` must use the same
enum type as `status`, and broad coverage claims.

Use [project status](../PROJECT_STATUS.md), [decisions](decisions.md), and the
[current outline](outline.md) for the active plan. The remaining Section 2
cleanup commits are summarized in the status document and Git history.

---

# Project Outline

Agreed stack: **Python + FastAPI** backend, **MySQL 8.4 LTS**, **React + TypeScript**
frontend, **VPN-only** remote access. Each section below is implemented on its own
branch/PR and only starts once verified by the project owner.

1. **Project Scaffolding & Conventions** — repo layout, FastAPI skeleton, Alembic,
    pytest/vitest harnesses, linting, dev run instructions.
  2. **Data Model & Database Schema** — SQLAlchemy models (Role, User, Material,
    Run, Measurement, AuditLog), migrations, ER diagram. Measured quantities and
    computed results are exact fixed-point: MySQL `DECIMAL(10,2)`, Python
    `Decimal` (never `float`); identifiers/counts/intervals are integers.
    Review outcome lives inline on Run (no separate ReviewRecord table).
    Run snapshots Material's *full* abnormality-rules set at creation
    (shared `AbnormalityRulesMixin`), not just standard_value. AuditLog
    has an indexed `action` field. Adds one `entry_method` column on
    Measurement (manual/automated) as the minimal hook for the Section 8
    ingestion portal, rather than a fuller speculative field set. Full
    schema, ER diagram, run state machine, and time policy:
    `docs/data-model.md`.
  3. **Authentication & Multi-Level Authorization** — server-side sessions
    (HTTP-only cookies), admin-invite-only account creation (no open
    self-registration). Roles: **Admin** (entry + review + user/config
    management), **Operator** (entry, no review), **Reviewer** (view + export
    only — does not itself approve/reject; that's an Admin action).
  4. **Core Domain Logic — Run Lifecycle (OOP service layer)** — `RunService`,
    `MeasurementService`, `AbnormalityDetector`, `ReviewService`.
  5. **Backend API Layer** — REST endpoints over the Section 4 services.
  6. **Search System** — attribute + date-range query/filter/sort/paginate.
  7. **Export System** — CSV + Excel + PDF export, built on the Section 6 query layer.
  8. **Extensible Data Input Portal** — pluggable "data formalizer" ingestion layer
    (Strategy pattern) so future automated/robotic data sources can be normalized
    into the Run/Measurement schema without touching manual-entry code paths.
    (Explicitly requested by the project owner for future robotic/automated
    detection lines; not part of the original 6-goal list, added deliberately.)
  9. **Frontend — Auth & App Shell** — login (admin-created accounts, no
    self-registration screen), auth context, role-guarded routing,
    sidebar/header layout.
  10. **Frontend — Overview Screen** — KPI tiles, recent runs, status distribution.
  11. **Frontend — Runs List Screen** — filterable/sortable table + filter panel
    (reused in Section 13).
  12. **Frontend — Run Entry Screen** — active/abnormal/closed run cards, editable
    measurement rows.
  13. **Frontend — Run Review Screen** — abnormal + normal review queues.
  14. **Frontend — Export Screen** — reuses the Section 11 filter panel + format
    selection.
  15. **Deployment & VPN Access** — WireGuard setup, service run config, MySQL
    backup/offline-storage procedure.
  16. **Documentation** — architecture, data-flow, ER, and class diagrams; finalized
    here but written incrementally as each section lands.

Unit tests and function-level comments are produced within every section as code
is written, not as a separate pass at the end.

## Decisions locked in during Section 1 review (2026-08-17)

- **Numeric representation**: exact fixed-point — MySQL `DECIMAL(10,2)` +
  Python `Decimal`, not `float`, for measured quantities and computed
  results. Identifiers/counts/intervals are plain integers.
- **Database**: MySQL 8.4 LTS specifically (not "MySQL/MariaDB"). CI's
  `mysql:8.4` service container matches production.
- **Reviewer role**: confirmed as view + export only by design — the name
  doesn't imply it performs the approve/reject action, Admin does.
- **Auth**: server-side sessions (HTTP-only cookies), not JWT. Accounts
  are admin-invite-only — no open self-registration, unlike the original
  design mockup's Login/Register screen.

## Decisions locked in during Section 2 review (2026-08-17)

- **Role**: normalized table + FK (not an enum column on User).
- **Review history**: inline fields on Run, no separate ReviewRecord table
  — a reviewed run's decision is final, no reopening.
- **Ingestion prep**: light touch — one `entry_method` column on
  Measurement (manual/automated), not the fuller speculative field set.
- **No closed-without-review path** — every run reaches its terminal
  state through review. See `docs/data-model.md` for the full state
  machine.

## Outline gap found while reading the mockup's actual logic (not just markup)

The design's `<script>` section (previously unread — only the template
markup had been reviewed) revealed real scope not yet reflected in
Sections 9–14 above:

- A **Materials standards management screen** (list/add/edit/deactivate
  Material, including its abnormality-detection rules) — no frontend
  section currently covers this.
- An **audit log viewer screen** (the AuditLog data Section 2 now
  models) — likewise uncovered.
- A second **daily-report export mode** (date + format, with a
  total/reviewed/abnormal/measurement-row summary) distinct from the
  filtered-runs export Section 14 already covers.

Not restructuring the section list unilaterally — flagging for the
project owner to decide where these land (new sections vs. folded into
existing ones) before Section 9 starts.

## Section 2 implementation review findings, fixed (2026-08-17)

- **Run now snapshots every `AbnormalityRulesMixin` field**, not just
  `standard_value` — the original version would have let a mid-run edit
  to a material's limits/thresholds judge earlier and later measurements
  in the same run by different rules, and made a closed run's history
  unreconstructable once its material moved on.
- **`AuditLog.action`** added (indexed) — without it, an audit row
  couldn't explicitly distinguish "run created" from "run reviewed" from
  "material deactivated", etc.
- **SQLite foreign-key enforcement enabled for the test fixture** — it's
  off by default, so the original `AuditLog.target_id`-has-no-FK test
  proved nothing (SQLite would have silently accepted *any* invalid FK,
  declared or not). Confirmed by reproducing the false-pass, then adding
  tests proving `User.role_id`/`Run.material_id`/`Measurement.run_id`
  genuinely reject bad references.
- **Time policy defined**: every timestamp is UTC by convention,
  generated in application code (`app.core.time.utcnow()`) rather than
  by the database server, specifically so correctness doesn't depend on
  the MySQL server's timezone configuration. See `docs/data-model.md`.
- **Numeric policy wording corrected** — "DECIMAL(10,2) everywhere" was
  overbroad; identifiers/counts/intervals were already correctly
  integers in code, the docs just didn't say so.
- **Indexing for Search recorded as an explicit Section 6 dependency**
  (not implemented yet) — see `docs/data-model.md`.

## Section 2 second-round review findings, fixed (2026-08-17)

- **`pending_from` now has a CHECK constraint restricting it to
  active/abnormal/NULL.** The column has to share `RunStatus`'s full
  enum type (it stores one of that same set of values), so without this
  constraint `pending_from='reviewed'` was silently accepted despite
  being nonsensical — confirmed by a test that assigns
  `RunStatus.REVIEWED` (a legitimate enum member, so it passes
  `sa_enum`'s validation) and checks the DB itself now rejects it.
- **Structural CHECK constraints added** on both `materials` and `runs`
  (sharing `AbnormalityRulesMixin`, so declared once via
  `abnormality_rule_constraints()` and applied to both tables — MySQL
  requires constraint names unique per-database, not per-table, hence
  the table-name-prefixed names): `lower_limit <= upper_limit`,
  `thickness_min <= thickness_max`, `deviation_pct_threshold >= 0`, plus
  `runs.interval_seconds > 0` and `runs.end_time >= start_time`.
  Verified SQLite enforces CHECK constraints by default (unlike foreign
  keys, which needed an explicit pragma).
- **Status-conditional invariants deliberately left to Section 4**, not
  encoded as CHECK constraints: e.g. `status=reviewed` implying
  `reviewed_by`/`review_resolution`/`reviewed_at` are set, or
  `status=active` implying they aren't. These are workflow transitions
  owned by `RunService`/`ReviewService` (the sole writers of those
  columns) and are better tested comprehensively there than encoded as
  CHECK expressions that would need a migration every time the state
  machine evolves. Documented directly in `Run`'s docstring so this
  reads as a decision, not an oversight.
- **Migration seed data is now actually verified in CI** — the existing
  `test_role_seed_values_are_distinct` unit test only proved Role *can*
  hold three distinct rows; it never touched the migration's own
  `op.bulk_insert`, so a typo'd or dropped seed would have gone
  uncaught. Added `backend/scripts/verify_seed_data.py`, run in CI
  between `alembic upgrade head` and `alembic downgrade base`, asserting
  the exact seeded codes and UTF-8 display names. Verified the script
  both passes on correct data and fails on deliberately corrupted data
  before trusting it in CI.

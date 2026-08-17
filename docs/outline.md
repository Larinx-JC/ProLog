# Project Outline

Agreed stack: **Python + FastAPI** backend, **MySQL 8.4 LTS**, **React + TypeScript**
frontend, **VPN-only** remote access. Each section below is implemented on its own
branch/PR and only starts once verified by the project owner.

1. **Project Scaffolding & Conventions** — repo layout, FastAPI skeleton, Alembic,
    pytest/vitest harnesses, linting, dev run instructions.
  2. **Data Model & Database Schema** — SQLAlchemy models (Role, User, Material,
    Run, Measurement, AuditLog), migrations, ER diagram. Numeric fields are
    exact fixed-point throughout: MySQL `DECIMAL(10,2)`, Python `Decimal`
    (never `float`). Review outcome lives inline on Run (no separate
    ReviewRecord table). Adds one `entry_method` column on Measurement
    (manual/automated) as the minimal hook for the Section 8 ingestion
    portal, rather than a fuller speculative field set. Full schema, ER
    diagram, and run state machine: `docs/data-model.md`.
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

- **Numeric representation**: exact fixed-point — MySQL `DECIMAL(p,2)` +
  Python `Decimal` end to end, not `float`.
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

# Project Outline

Agreed stack: **Python + FastAPI** backend, **MySQL/MariaDB**, **React + TypeScript**
frontend, **VPN-only** remote access. Each section below is implemented on its own
branch/PR and only starts once verified by the project owner.

1. **Project Scaffolding & Conventions** — repo layout, FastAPI skeleton, Alembic,
   pytest/vitest harnesses, linting, dev run instructions.
2. **Data Model & Database Schema** — SQLAlchemy models (Users, Roles, Materials,
   Runs, Measurements, ReviewRecords, AuditLog), migrations, ER diagram. Numeric
   fields are consistently 2-decimal fixed-point values throughout; exact
   representation is an open question below.
3. **Authentication & Multi-Level Authorization** — roles: **Admin** (entry + review),
   **Operator** (entry, no review), **Reviewer** (view + export only, no entry/edit).
4. **Core Domain Logic — Run Lifecycle (OOP service layer)** — `RunService`,
   `MeasurementService`, `AbnormalityDetector`, `ReviewService`.
5. **Backend API Layer** — REST endpoints over the Section 4 services.
6. **Search System** — attribute + date-range query/filter/sort/paginate.
7. **Export System** — Excel + PDF export, built on the Section 6 query layer.
8. **Extensible Data Input Portal** — pluggable "data formalizer" ingestion layer
   (Strategy pattern) so future automated/robotic data sources can be normalized
   into the Run/Measurement schema without touching manual-entry code paths.
   (Explicitly requested by the project owner for future robotic/automated
   detection lines; not part of the original 6-goal list, added deliberately.)
9. **Frontend — Auth & App Shell** — login/register, auth context, role-guarded
   routing, sidebar/header layout.
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

## Open questions before Section 2

Flagged by Section 1 review, needs the project owner's decision:

- **Numeric representation**: SQL `DECIMAL` + Python `Decimal` (exact
  fixed-point, recommended) vs. `float` rounded to 2 places (simpler, but
  binary floats can't guarantee exact 2-decimal storage). Affects DB
  columns, Pydantic schemas, API serialization, and frontend formatting.
- **Database vendor/version**: repo currently says "MySQL/MariaDB" —
  needs one specific target (e.g. MySQL 8.4 LTS) before migrations are
  written. CI now runs against `mysql:8.4` as a working default.
- **Reviewer role semantics**: as specified, "Reviewer" is view + export
  only (no approve/reject), while `ReviewService.approve()/reject()` in
  Section 4 is presumably called by Admin. Confirm this is intentional
  (the role named "Reviewer" doesn't itself review) before Section 3.
- **Auth mechanism**: server-side sessions vs. JWT access/refresh tokens
  — not yet decided. Also confirm whether registration should stay
  self-service (as in the original design mockup) or become admin-invite-
  only, given the "permitted users only" requirement.

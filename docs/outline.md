# Project Outline

Agreed stack: **Python + FastAPI** backend, **MySQL/MariaDB**, **React + TypeScript**
frontend, **VPN-only** remote access. Each section below is implemented on its own
branch/PR and only starts once verified by the project owner.

1. **Project Scaffolding & Conventions** — repo layout, FastAPI skeleton, Alembic,
   pytest/vitest harnesses, linting, dev run instructions.
2. **Data Model & Database Schema** — SQLAlchemy models (Users, Roles, Materials,
   Runs, Measurements, ReviewRecords, AuditLog), migrations, ER diagram. Numeric
   fields are `DECIMAL` with 2-decimal precision throughout.
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

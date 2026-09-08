# Project outline

This is the current delivery plan. See [project status](../PROJECT_STATUS.md)
for the approved stage and evidence, [decisions](decisions.md) for confirmed
choices, and [CONTRIBUTING](../CONTRIBUTING.md) for the section approval process.
Historical review discussions are in [review history](review-history.md).

The original 16 section numbers and names remain stable. Additional screens
are explicit deliverables within the existing sections.

1. **Project Scaffolding & Conventions** — FastAPI and React/TypeScript
   scaffolding, configuration, conda development setup, migrations, test
   harnesses, linting, type checking, and CI.
2. **Data Model & Database Schema** — Role, User, Material, Run, Measurement,
   and AuditLog; full detection-rule snapshot on Run; inline final review
   outcome; structural constraints; UTC conventions; decimal quantities and
   integer identifiers/intervals; initial migration and seed verification.
   Measurement.entry_method reserves the manual/automated distinction.
   See [data model](data-model.md).
3. **Authentication & Multi-Level Authorization** — first Admin setup,
   Admin-issued single-use activation links, login/logout, server-side
   sessions, password change/recovery, user administration, and reusable
   permission checks. Auth and user-management APIs belong here.
   See [Section 3 acceptance checklist](sections/03-authentication.md).
4. **Core Domain Logic — Run Lifecycle (OOP service layer)** — RunService,
   MeasurementService, AbnormalityDetector, and ReviewService own production
   writes. Define and test every transition, full rule copying, snapshot
   immutability, review consistency, audit atomicity, repeated requests, and
   simultaneous edits. Add material-rule administration services and audit
   events. Resolve self-review policy and calculation rules before coding
   dependent behavior; see [decisions](decisions.md) and the
   [Section 4 acceptance plan](sections/04-run-lifecycle.md).
5. **Backend API Layer** — production endpoints for runs, measurements,
   closure, Admin review, materials, audit-log reads, and overview aggregates.
   Reuse Section 3 authentication and Section 4 services; validate the API
   data contract. Raw ORM writes must not bypass production services.
6. **Search System** — shared permission-aware filtering, sorting, and
   pagination for runs, measurements, materials, and audit logs. Define
   attributes, timezone/date boundaries, indexes, expected data volume, and
   a measurable response-time target. Export reuses the same filter logic.
7. **Export System** — CSV, Excel/XLSX, and PDF. Cover selected/filtered runs
   and daily reports (totals, reviewed/abnormal runs, measurement counts).
   Obtain the owner's Excel/PDF samples here. Define row limits, audit events,
   file formatting, and whether large exports need background jobs.
8. **Extensible Data Input Portal** — authenticated intake with pluggable
   formalizers mapping source payloads to the common domain types and
   production services. Design source identity, deduplication, timestamps,
   validation failures, raw-data retention, and further migrations here.
9. **Frontend — Auth & App Shell** — login, invitation activation, password
   change/recovery, Admin account management, session-expiry handling,
   permission-aware routing, sidebar, and header using the local design.
10. **Frontend — Overview Screen** — KPI tiles, recent runs, status
    distribution, and visible refresh/error/stale-data states. Agree on
    monitoring refresh behavior before implementation.
11. **Frontend — Runs List Screen** — 11A: run search/list/detail and reusable
    filters/tables; 11B: materials standards list/add/edit/deactivate;
    11C: permission-aware audit-log viewer. These are one section's explicit
    deliverables, reusing Sections 5–6 APIs and common UI components.
12. **Frontend — Run Entry Screen** — new-run entry, active/abnormal runs,
    measurement recording, missing-data states, conflict feedback, and
    closure for review. Preserve server validation and decimal representation.
13. **Frontend — Run Review Screen** — Admin review queues, decision/reason
    entry, and terminal reviewed-run display. The role named Reviewer keeps
    its agreed view/export-only permissions.
14. **Frontend — Export Screen** — reuse Section 11 filters and selection;
    add CSV/XLSX/PDF downloads and daily-report date/format controls.
15. **Deployment & VPN Access** — Windows startup/restart, VPN access,
    HTTPS reverse proxy, firewall and stable LAN addressing, restricted MySQL
    access, backup retention/encryption, restore verification, logs, and health
    monitoring. Confirm actual host topology and retention before deployment.
16. **Documentation** — finalize operating, administrator, recovery, and
    developer guides with architecture, workflow/data flow, variable types,
    database, and class relationships. Documentation grows with every section.

## Acceptance across sections

Each section has written acceptance criteria, tests for important behavior,
function documentation, a demonstration procedure, and a PR with evidence for
its exact commit. Follow [the testing plan](testing.md) for current checks and
scheduled improvements. Passing CI and owner verification are separate events.

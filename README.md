# ProLog

Production monitoring, recording, and review system for a sheet-resistance
detection line (方阻检测产线). Runs on-site with the database stored locally;
authorized users can reach it remotely over VPN only.

## Stack

- **Backend:** Python + FastAPI
- **Database:** MySQL 8.4 LTS
- **Frontend:** React + TypeScript
- **Remote access:** VPN only (no public internet exposure)

## Workflow

1. **Enter** a new run
2. **Record** measurements while the run is active, with automatic
   abnormality detection against the material's full rule set (standard
   value, upper/lower limits, thickness bounds, deviation threshold) —
   snapshotted onto the run at creation, so a later edit to the
   material's rules never changes how an existing run is judged
3. **Review and close** the run (separate queues for normal vs. abnormal runs)

Plus: cross-cutting search (by attribute/date) and export (CSV/Excel/PDF)
over all run and measurement data, and a role system — **Admin** (entry, review,
user/config management), **Operator** (entry only), **Reviewer** (view +
export only). Accounts are admin-invite-only; there's no open
self-registration.

## Repository layout

This repo is being built section by section against a written outline
(see [docs/outline.md](docs/outline.md)); each section lands as its own
PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching/PR workflow.

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, pytest
frontend/   React + TypeScript app (Vite), vitest
docs/       Outline, architecture, data-flow, schema docs (grows per section)
```

## Getting started

### Backend

Uses a dedicated conda environment named `prolog` (Python 3.12).

```
conda create -n prolog python=3.12   # first time only
conda activate prolog
cd backend
pip install -r requirements-lock.txt  # pinned, reproducible versions
pip install -e . --no-deps
copy .env.example .env                # then edit DATABASE_URL etc.
uvicorn app.main:app --reload
```

Run tests: `pytest` (from `backend/`). Lint: `ruff check .`. Type-check: `mypy app`.
Regenerating `requirements-lock.txt` after changing dependencies: see the
comment at the top of that file.

### Frontend

```
cd frontend
npm install
copy .env.example .env
npm run dev
```

Run tests: `npm test -- --run` (from `frontend/`). Lint: `npm run lint`.

## Status

Section 1 (Project Scaffolding & Conventions) verified and merged.

Section 2 (Data Model & Database Schema) implemented and reviewed —
Role/User/Material/Run/Measurement/AuditLog models, migration verified
against real MySQL 8.4 (schema, CHECK constraints, and seeded reference
data all checked in CI), 100% test coverage. Awaiting sign-off; see
`docs/data-model.md` for the schema and `docs/outline.md` for decisions
locked in during review.

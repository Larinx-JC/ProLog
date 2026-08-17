# ProLog

Production monitoring, recording, and review system for a sheet-resistance
detection line (方阻检测产线). Runs on-site with the database stored locally;
authorized users can reach it remotely over VPN only.

## Stack

- **Backend:** Python + FastAPI
- **Database:** MySQL/MariaDB
- **Frontend:** React + TypeScript
- **Remote access:** VPN only (no public internet exposure)

## Workflow

1. **Enter** a new run
2. **Record** measurements while the run is active, with automatic
   abnormality detection against the material's standard value
3. **Review and close** the run (separate queues for normal vs. abnormal runs)

Plus: cross-cutting search (by attribute/date) and export (Excel/PDF) over
all run and measurement data, and a role system (Admin / Operator / Reviewer).

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

```
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
copy .env.example .env                            # then edit DATABASE_URL etc.
uvicorn app.main:app --reload
```

Run tests: `pytest` (from `backend/`). Lint: `ruff check .`. Type-check: `mypy app`.

### Frontend

```
cd frontend
npm install
copy .env.example .env
npm run dev
```

Run tests: `npm test -- --run` (from `frontend/`). Lint: `npm run lint`.

## Status

Section 1 (Project Scaffolding & Conventions) complete. See
[docs/outline.md](docs/outline.md) for what's next.

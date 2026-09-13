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
3. **Close the run for review**, then **record the review decision**
   (separate queues for normal vs. abnormal runs) — see the run state
   machine in [docs/data-model.md](docs/data-model.md)

Plus: cross-cutting search (by attribute/date) and export (CSV/Excel/PDF)
over all run and measurement data, and a role system — **Admin** (entry, review,
user/config management), **Operator** (view all runs; create/edit own eligible runs), **Reviewer** (view +
export only). Accounts are admin-invite-only; there's no open
self-registration.

## Repository layout

This repo is being built section by section against a written outline
(see [docs/outline.md](docs/outline.md)); each section lands as its own
PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching/PR workflow.

For the current handover, start with [PROJECT_STATUS.md](PROJECT_STATUS.md).
Confirmed choices are in [docs/decisions.md](docs/decisions.md); the
current section's checklist is [Section 4 run lifecycle](docs/sections/04-run-lifecycle.md).
The owner-added [Measurement & Accuracy Settings page](docs/sections/04-accuracy-settings.md)
is planned for Section 11D, with its backend policy and storage prepared in
Section 4. Initial thickness precision is three decimal places in mm;
the Section 4 backend/migration are implemented, reviewed and CI verified,
while the API and settings page remain scheduled for their later sections.
Admin-adjustable screen rounding is now separate from recording accuracy and
applies to existing and new runs. Canonical values and alarm results remain
unchanged; see the current display amendment in the status and review documents.

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
python -m alembic upgrade head
python -m app.cli bootstrap-admin --account admin.local --name Administrator
uvicorn app.main:app --reload
```

Run tests: `pytest` (from `backend/`). Lint: `ruff check .`. Type-check: `mypy app`.
Regenerating `requirements-lock.txt` after changing dependencies: see the
comment at the top of that file.

The bootstrap command prompts for a password and works only once. See
[authentication operations and API](docs/authentication.md) for activation,
recovery, session policy, configuration, and a repeatable demonstration.

### Frontend

```
cd frontend
npm install
copy .env.example .env
npm run dev
```

Run tests: `npm test -- --run` (from `frontend/`). Lint: `npm run lint`.

## Status

Sections 1–3 are verified and merged. Section 4's service layer and migration
are implemented, fully reviewed and CI verified; owner verification is pending.
See the [full review](docs/reviews/section-04-review.md),
[implementation guide](docs/run-lifecycle.md) and status page for evidence.

The React application is currently a scaffold. See
[PROJECT_STATUS.md](PROJECT_STATUS.md) for the tested commit, CI evidence,
local verification, and remaining work.

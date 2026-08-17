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

This repo is being built section by section against a written outline;
each section lands as its own PR. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the branching/PR workflow. `docs/` will hold the architecture,
data-flow, and schema documentation as sections land.

## Status

Scaffolding in progress — no application code yet.

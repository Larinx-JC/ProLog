# Workflow

This project uses **GitHub Flow** with a protected `main` branch.

## Branching

- `main` is always deployable and is protected: no direct pushes, no
  force-pushes, no deletion.
- All work happens on a short-lived feature branch cut from `main`:
  `section/<n>-<slug>`, e.g. `section/02-data-model`.
- One feature branch per outline section (see project outline in the
  original planning conversation / `docs/outline.md` once added).

## Pull requests

- Every change to `main` goes through a PR.
- A PR requires:
  - At least 1 approving review.
  - All required CI checks passing (lint, backend tests, frontend tests —
    see `.github/workflows/ci.yml`).
  - Branch up to date with `main` before merge.
- Prefer squash-merge so `main` history reads one commit per logical change.

## Commits

- Keep commits scoped to one logical change.
- Reference the outline section in the PR description (e.g. "Section 4:
  Run lifecycle domain services").

## Tests and comments

- Every non-trivial function gets a unit test and a short comment
  explaining *why* (not what) where it isn't obvious from the code itself.
- Numeric fields are consistently 2-decimal floats end to end (DB, API,
  UI) — see `docs/data-types.md` once Section 2 lands.

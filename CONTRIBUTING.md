# Workflow

This project follows **GitHub Flow** in spirit, adapted for a solo developer
on a free-tier private repo (GitHub-enforced branch protection needs GitHub
Pro or an org on a private repo, and GitHub won't let you approve your own
PR anyway — see the repo's own "Skip enforced protection for now" decision).
Nothing below is technically blocked by GitHub; it's the process we're
choosing to follow by discipline.

## Branching

- `main` is meant to always be deployable.
- Work happens on a short-lived feature branch cut from `main`:
  `section/<n>-<slug>`, e.g. `section/02-data-model`.
- One feature branch per outline section (see `docs/outline.md`).
- Direct pushes to `main` are discouraged but not technically blocked.

## Pull requests

- Every change lands via a PR — this is a self-review record (a chance to
  read the diff as a whole and let CI run) rather than an approval gate.
- No independent approving review is required while there's a single
  developer on the project.
- All CI checks must pass (lint, backend-tests, frontend-tests — see
  `.github/workflows/ci.yml`) before merging.
- Prefer squash-merge so `main` history reads one commit per logical change.

## Commits

- Keep commits scoped to one logical change.
- Reference the outline section in the PR description (e.g. "Section 4:
  Run lifecycle domain services").

## Tests and comments

- Every non-trivial function gets a unit test and a short comment
  explaining *why* (not what) where it isn't obvious from the code itself.
- Measured physical quantities and calculated numeric results are
  consistently 2-decimal fixed-point values end to end: MySQL
  `DECIMAL(10,2)`, Python `Decimal` (never `float`), Pydantic constrained
  `Decimal`. Identifiers, counts, and whole-second intervals use plain
  integers instead — see `docs/data-model.md`.

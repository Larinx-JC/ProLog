# Workflow

This project uses section branches, pull requests, passing CI, and explicit
owner verification. GitHub branch protection is not enabled for this repository.
The process below is followed by the owner and implementation agent.

Start with [project status](PROJECT_STATUS.md), the [outline](docs/outline.md),
and [decisions](docs/decisions.md).

## Section workflow

1. Write the section's acceptance checklist and resolve decisions that affect
   its implementation. Separate agreed requirements from proposed defaults.
2. Obtain the owner's authorization to advance from the previous section.
   The required form is:

   > Yes, I verify the production of {completed section name} and you can proceed to the production of {next section name}.

3. Merge the verified previous section after checking CI for its current head,
   then start the next section's branch. Once authorized, routine work and
   corrections within that section do not require repeated approval.
4. Implement important behaviors with tests and function documentation.
   Keep commits scoped and maintain the section's acceptance evidence.
5. Review the entire section diff against its base: implementation, migrations,
   tests, documentation, and agreed requirements. Record findings, their
   severity, verification evidence, and untested limits. Reviewing only the
   latest correction or checking green CI is insufficient. After fixes, review
   the affected changes and rerun relevant verification. Demonstrate the
   behavior, update documentation, and only then present the PR for verification.
6. Wait for the owner's next section-verification statement before merging
   and advancing. A review comment, "ok" to planning, or passing CI alone
   does not satisfy the explicit section gate.

## Branching

- `main` is meant to always be deployable.
- Work happens on a short-lived feature branch cut from `main`:
  `section/<n>-<slug>`, e.g. `section/02-data-model`.
- One feature branch per outline section (see `docs/outline.md`).
- Direct pushes to `main` are discouraged but not technically blocked.

## Pull requests

- Every change lands via a PR with a reviewable diff, demonstration procedure,
  and verification evidence for the current commit.
- No independent approving review is required while there's a single
  developer on the project.
- All CI checks must pass (lint, Windows/Linux backend-unit, mysql-integration,
  and frontend-tests — see
  `.github/workflows/ci.yml`) before merging.
- Prefer squash-merge so `main` history reads one commit per logical change.
- Use [.github/pull_request_template.md](.github/pull_request_template.md).
  Record the section approval separately from technical test results.
- Keep fixes to the current section on its open PR. After an approved migration
  is merged, extend it with a new revision; do not rewrite migration history.

## Commits

- Keep commits scoped to one logical change.
- Reference the outline section in the PR description (e.g. "Section 4:
  Run lifecycle domain services").

## Tests and comments

- Every written function has a short comment/docstring explaining its purpose
  and non-obvious assumptions. Important functions have success, rejection,
  and error-path tests appropriate to their behavior.
- Follow [the testing plan](docs/testing.md): behavioral assertions, selected
  MySQL integration checks, deterministic time tests, and scoped coverage.
  State what a passing check actually proves and what was not executed.
- Measured physical quantities and calculated numeric results are
  consistently 2-decimal fixed-point values end to end: MySQL
  `DECIMAL(10,2)`, Python `Decimal` (never `float`), Pydantic constrained
  `Decimal`. Identifiers, counts, and whole-second intervals use plain
  integers instead — see `docs/data-model.md`.

## Documentation and handovers

- Keep [PROJECT_STATUS.md](PROJECT_STATUS.md) current with the section state,
  tested commit, CI evidence, next gate, and links.
- Record confirmed decisions in [docs/decisions.md](docs/decisions.md).
  Link each deferred requirement to its owning section.
- Keep the active [outline](docs/outline.md) concise. Historical reviews live
  in [review history](docs/review-history.md).
- For documentation-only changes, check links, Markdown structure, and the
  complete diff. Do not claim application tests were rerun if they were not.

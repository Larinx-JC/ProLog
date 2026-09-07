# Project status

Updated: 2026-09-07. This is the starting point for project handovers.

## Current stage

| Section | State | Evidence / next action |
| --- | --- | --- |
| 1 — Project Scaffolding & Conventions | Owner verified; merged | Main contains squash commit `3163e45`. |
| 2 — Data Model & Database Schema | Implemented; awaiting owner verification | [PR #2](https://github.com/Larinx-JC/ProLog/pull/2), branch `section/02-data-model`, implementation baseline `e98da3f`. |
| 3 — Authentication & Multi-Level Authorization | Acceptance checklist prepared; implementation not authorized yet | [Section 3 checklist](docs/sections/03-authentication.md). |
| 4–16 | Planned | [Current outline](docs/outline.md). |

The owner authorized the workflow/documentation improvements on 2026-09-07.
That authorization does not verify Section 2 or authorize Section 3 code.
The current changes update documentation and the PR template on the open
Section 2 branch; they do not change the schema or application behavior.

## Verified implementation baseline

- Commit: `e98da3f86b2e083df3c1eb6d45cdef7189f0aed3`.
- [GitHub Actions run 32051698488](https://github.com/Larinx-JC/ProLog/actions/runs/32051698488):
  lint, backend-tests, and frontend-tests succeeded.
- Local handover check on 2026-09-07: Ruff and mypy passed; 43 backend tests
  passed using the existing `prolog` conda environment; frontend lint,
  one test, TypeScript compilation, and Vite production build passed.
- The sandbox initially prevented two tests from creating temporary files.
  The authorized rerun outside the sandbox passed all 43 tests.
- MySQL evidence comes from GitHub CI. The handover did not run a local
  MySQL service or a local MySQL migration cycle.
- Previous coverage reports measured 100% app statements and approximately
  99% overall, including tests/scripts. The handover did not rerun coverage.
  Those percentages do not establish unimplemented service behavior.

These results apply to the named baseline. For later commits, inspect the
PR's checks and match their commit before reporting them as verified.

## What exists and what comes next

The backend contains configuration, a health endpoint, ORM models, a migration,
and tests. The React app is a scaffold placeholder. Authentication, production
services, operational screens, search, exports, ingestion, and deployment
remain to be implemented through their approved sections.

The local design is in `prototype/Production Dashboard Frontend/`, including
`Product Status Dashboard.dc.html`, `Login.dc.html`, `support.js`, and images.
This directory is currently untracked and has been left unchanged. Include
design-source versioning in Section 9 preparation after inspecting the assets;
do not silently stage the directory during unrelated commits.

## Decisions and follow-ups

- [Confirmed decisions and open choices](docs/decisions.md) are authoritative.
- Invitation delivery: Admin copies a single-use activation link and shares
  it through an existing trusted channel; application email delivery is not
  required. Confirmed by the owner on 2026-09-07.
- Session defaults: 30 minutes inactive, 12 hours absolute maximum;
  configurable, with background dashboard refresh excluded from activity.
  Confirmed by the owner on 2026-09-07.
- [Testing improvements](docs/testing.md) are assigned to the sections where
  the relevant code is introduced. Windows CI and MySQL behavior tests are
  scheduled, not already implemented.
- Section 3 must settle remaining account/permission details in its checklist.
  Section 4 must settle calculation rules, factory timezone, and self-review.
- Excel/PDF samples are requested in Section 7, as agreed.

## Approval needed to advance

The next owner verification statement is:

> Yes, I verify the production of Data Model & Database Schema and you can proceed to the production of Authentication & Multi-Level Authorization.

After that statement and passing checks for the current PR head, merge PR #2
and start Section 3. See [CONTRIBUTING](CONTRIBUTING.md) for the complete
section workflow and [review history](docs/review-history.md) for past reviews.

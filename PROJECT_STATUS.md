# Project status

Updated: 2026-09-07. This is the starting point for project handovers.

## Current stage

| Section | State | Evidence / next action |
| --- | --- | --- |
| 1 — Project Scaffolding & Conventions | Owner verified; merged | Main contains squash commit `3163e45`. |
| 2 — Data Model & Database Schema | Owner verified and merged | [PR #2](https://github.com/Larinx-JC/ProLog/pull/2), squash `6b0509e`; final closeout CI `34085202115` passed. |
| 3 — Authentication & Multi-Level Authorization | Implemented locally; MySQL/CI verification and full review in progress | Branch `codex/section-03-authentication`; [checklist](docs/sections/03-authentication.md), [implementation brief](docs/sections/03-implementation.md). |
| 4–16 | Planned | [Current outline](docs/outline.md). |

After receiving the full Section 2 review, the owner verified Section 2 and
authorized Section 3 on 2026-09-07. The remaining non-blocking default-parity
and function-documentation findings will be resolved during Section 3.
Section 2 closeout recorded the review and approval without changing behavior.
Section 3 adds authentication, a new migration, and expanded verification.

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

## Full Section 2 review

The owner requires a full section review before any approval request.
The [review report](docs/reviews/section-02-review.md) covers the complete
Section 2 diff at `a91c6ee` against Section 1 (`3163e45`).
All 43 backend tests, Ruff, mypy, and `pip check` passed again on 2026-09-07;
additional migrated-SQLite checks passed. The exact head's GitHub CI passed,
including MySQL 8.4 migration, drift, and seed steps.

No production-blocking schema defect was found. A mismatch between ORM and
migration server defaults, plus missing function comments, remains as
recommended cleanup. The owner subsequently approved Section 2 with these
findings visible. Track their correction and verification in Section 3;
retain the original review findings as history.

## What exists and what comes next

The backend now includes authentication services/APIs, local Admin setup,
server-side sessions, activation/recovery grants, and related tests. This work
is undergoing Section 3 verification. The React app remains a scaffold;
authentication screens arrive in Section 9. Production services, operational
screens, search, exports, ingestion, and deployment belong to later sections.

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
- Section 3 account/permission choices were confirmed in the owner replies.
  Section 4 must settle calculation rules, factory timezone, and self-review.
- Excel/PDF samples are requested in Section 7, as agreed.

## Section approval record

Received from the owner on 2026-09-07:

> Yes, I verify the production of Data Model & Database Schema and you can proceed to the production of Authentication & Multi-Level Authorization.

PR #2 merged after its final checks passed. A complete Section 3 review must
precede its next approval request;
Section 4 is not authorized. See [CONTRIBUTING](CONTRIBUTING.md) for the complete
section workflow and [review history](docs/review-history.md) for past reviews.

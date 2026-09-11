# Project status

Updated: 2026-09-11. This is the starting point for project handovers.

## Current stage

| Section | State | Evidence / next action |
| --- | --- | --- |
| 1 — Project Scaffolding & Conventions | Owner verified; merged | Main contains squash commit `3163e45`. |
| 2 — Data Model & Database Schema | Owner verified and merged | [PR #2](https://github.com/Larinx-JC/ProLog/pull/2), squash `6b0509e`; final closeout CI `34085202115` passed. |
| 3 — Authentication & Multi-Level Authorization | Owner verified and merged | [PR #3](https://github.com/Larinx-JC/ProLog/pull/3), squash `f7bee48`; [full review](docs/reviews/section-03-review.md). |
| 4 — Core Domain Logic — Run Lifecycle (OOP service layer) | Implemented, fully reviewed and CI verified; awaiting owner verification | Branch `codex/section-04-run-lifecycle`, draft PR #4; [full review](docs/reviews/section-04-review.md), [acceptance](docs/sections/04-run-lifecycle.md), [implementation](docs/run-lifecycle.md). Unmerged; Section 5 remains gated. |
| 5–16 | Planned | [Current outline](docs/outline.md). |

After receiving the full Section 2 review, the owner verified Section 2 and
authorized Section 3 on 2026-09-07. The remaining non-blocking default-parity
and function-documentation findings are resolved in Section 3.
Section 2 closeout recorded the review and approval without changing behavior.
Section 3 adds authentication, a new migration, and expanded verification.

On 2026-09-08 the owner explicitly confirmed Section 3 and approved moving to
Section 4. The exact approved head `21e7c6a` had all five checks passing in
[CI run 34185911703](https://github.com/Larinx-JC/ProLog/actions/runs/34185911703).
PR #3 was merged, and Section 4's branch starts from squash `f7bee48`.

## Section 3 verification

Full-review implementation baseline: `8a44eb4`, based on merged Section 2 `6b0509e`.
The full review covers every section file, including migrations, tests,
dependencies, CI, documentation and the owner's confirmed D14–D18 choices.
Findings and corrections are recorded in the [review](docs/reviews/section-03-review.md).
[CI run 34159260847](https://github.com/Larinx-JC/ProLog/actions/runs/34159260847)
passed all five jobs for `8a44eb4`: 129 backend tests on each of Windows/Linux,
eight MySQL 8.4 integration tests, lint and frontend lint/test/build.
Local verification used only the existing `prolog` conda environment: 129 tests,
Ruff, mypy and `pip check` passed; scoped app/script coverage was 924/926
statements. The two uncovered statements are CLI/script module dispatch.
MySQL was exercised in CI, not on a locally installed service.
The subsequent owner-reported `_env_file` editor diagnostic is corrected in
shared test configuration. Pyright now reports zero errors/warnings in the
five affected files, and 130 local backend tests pass. See the review addendum
and PR #3 for the correction and exact-head CI evidence. The approved merged
baseline is `f7bee48`; no Section 4 application behavior is claimed by these checks.

## Historical Section 2 baseline

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

No production-blocking schema defect was found. At review time, ORM/migration
default mismatch and missing function comments remained as recommended cleanup.
The owner approved Section 2 with those findings visible. Both are corrected
and verified in Section 3; the original review remains historical evidence.

## What exists and what comes next

The backend includes verified authentication services/APIs, local Admin setup,
server-side sessions, activation/recovery grants, and related tests. Section 4
now has implemented domain services. The owner confirmed Asia/Shanghai, Ω/mm/m/min/m
units, Admin self-review with a required audited reason, and an Admin-configurable
initial 2.00% deviation tolerance. The owner then selected target deviation
for the alarm, uniformity as a separate statistic, three-place thickness in mm,
and an Admin accuracy settings portal. The outline now includes backend policy
and storage in Section 4, endpoints in Section 5, and a new settings page in
Section 11D. Migration `b6d84e19a203` adds six-place storage, immutable accuracy
versions, operational settings, retry receipts and sampling/closure metadata.
D24–D29 confirm rounding, completeness/closure, 0–6 supported places,
factory-wide precision, current Operator controls and scheduled samples.
The full Section 4 diff was reviewed against `f7bee48` on 2026-09-11, including
domain logic, services, migration, tests, dependency changes and documentation.
The [review](docs/reviews/section-04-review.md) records corrected findings and
acceptance evidence. MySQL CI passed all five jobs for `63dc7b6` in
[run 34563625649](https://github.com/Larinx-JC/ProLog/actions/runs/34563625649),
including the corrected rollback and independent-connection tests. The final
reviewed implementation `f3441973a89710a2f37c7affe0b53a1fa85f2874` passed all five
jobs in [CI 34567271585](https://github.com/Larinx-JC/ProLog/actions/runs/34567271585):
254 backend tests on each Windows/Linux runner, 19 actual MySQL integration
tests, migration/seed/drift/downgrade checks, lint and frontend lint/test/build.
Follow-up changes only record this evidence and update the section handover.
The PR's checks identify the current documentation head separately.
Local final verification passed 254 backend tests, Ruff, mypy and `pip check`;
scoped app/script coverage was 1,611/1,613 statements. Frontend lint, one test,
TypeScript compilation and Vite build passed. MySQL is verified in CI only.
The React app remains a scaffold;
authentication screens arrive in Section 9. Production APIs, operational
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
- [Testing improvements](docs/testing.md) now include Windows/Linux backend
  unit CI, scoped coverage, deterministic clocks, and migrated MySQL behavior
  tests. The review records exact-run evidence and deployment limits.
- Section 3 account/permission choices were confirmed in the owner replies.
  Section 4 choices D19–D29 resolve Q04–Q06/Q12. The acceptance and implementation
  documents record the selected calculations, defaults, controls, workflow,
  migration and verification requirements.
- Excel/PDF samples are requested in Section 7, as agreed.

## Section approval record

Received from the owner on 2026-09-07:

> Yes, I verify the production of Data Model & Database Schema and you can proceed to the production of Authentication & Multi-Level Authorization.

PR #2 merged after its final checks passed. A complete Section 3 review must
precede its approval request; that review and its correction follow-up were
completed before the owner replied on 2026-09-08:

> Ok, I confirm section 3 and I approve to move to section 4

This explicit approval authorizes Section 4. PR #3 merged after its exact-head
checks were confirmed. Section 5 is not authorized. See
[CONTRIBUTING](CONTRIBUTING.md) for the section workflow and
[review history](docs/review-history.md) for past reviews.

# Section 2 full review

Reviewed: 2026-09-07, by the implementation assistant in a separate review pass.
This is an independent inspection of the inherited implementation, not an
independent human approval.

Base: `3163e45` (verified Section 1 on `origin/main`).
Head: `a91c6eed80dc40b1262c65fca692dc36f200636a`.
Scope: the complete Section 2 diff against its base, including all previous
review corrections and the workflow documentation added at the head.

## Verdict

No production-blocking schema defect found within the agreed Section 2 scope.
One medium verification/parity issue and one low documentation issue remain.
I recommend correcting these before owner sign-off, then reviewing the fixes
and rerunning their relevant checks. Green CI alone is not the full review.
This report does not approve Section 2, merge PR #2, or authorize Section 3.

## Findings

### R2-01 — Medium: server defaults differ between metadata and migration

Locations: [User](../../backend/app/models/user.py),
[rule mixin](../../backend/app/models/mixins.py),
[Material](../../backend/app/models/material.py),
[Run](../../backend/app/models/run.py),
[Measurement](../../backend/app/models/measurement.py),
[initial migration](../../backend/alembic/versions/0c3dff882627_initial_schema.py),
and [Alembic environment](../../backend/alembic/env.py).

The migration supplies database defaults for 12 columns, while the ORM defines
Python-side `default=` only:

| Table | Columns |
| --- | --- |
| users | is_active, must_change_password |
| materials | is_active, deviation_check_enabled, thickness_check_enabled, limits_check_enabled |
| runs | status, deviation_check_enabled, thickness_check_enabled, limits_check_enabled |
| measurements | status, entry_method |

Observed with SQLAlchemy inspection after executing the actual migration on a
disposable SQLite database. Raw inserts omitting these columns succeeded on
that migrated schema. Metadata-created tables have no matching database
defaults, so raw SQL has different behavior in the current test schema.
ORM inserts currently supply matching values; this is not evidence that
production writes already save wrong values.

`alembic check` still passes because `env.py` does not enable server-default
comparison. Alembic disables that comparison by default, so the current check
cannot prove default parity. See the
[Alembic configuration documentation](https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.environment.EnvironmentContext.configure.params.compare_server_default).

Recommended correction: declare matching `server_default` values in ORM
metadata, retain matching Python defaults where useful, and enable/test
server-default comparison against MySQL 8.4. Include a regression that detects
an intentionally changed default. Preserve application-generated UTC timestamp
defaults; this recommendation does not add database `NOW()` defaults.

### R2-02 — Low: a few written functions lack their own explanation

Locations: `main()` in [seed verifier](../../backend/scripts/verify_seed_data.py),
`upgrade()`/`downgrade()` in the
[migration](../../backend/alembic/versions/0c3dff882627_initial_schema.py), and the
six model `__repr__()` methods.

The module/class documentation explains much of their purpose, and important
logic has tests. However, these functions lack their own short purpose
comment/docstring, while the owner's explicit rule covers every written
function. Add concise function docstrings as a small convention cleanup.
No additional tests are needed solely for adding comments.

## Review coverage

| Area | Inspected and verified |
| --- | --- |
| Models and relationships | All six ORM entities, shared enums/mixins, imports/metadata registration, FK targets, nullability, uniqueness, decimal types, lifecycle fields, and all nine CHECK expressions. |
| Migration | Every table/column, FK/index/CHECK, literal enum values, role codes/names/descriptions, ordering, and downgrade with populated synthetic data. |
| Supporting backend | UTC helper, session dependency, configuration/percent escaping, Alembic environment, seed-verifier logic and command entry point. |
| Tests | Every backend test/fixture, success and rejection assertions, SQLite FK enforcement, snapshot independence, interval boundaries, UTC tests, seed success/mismatch paths, and coverage scope. |
| Build/CI | Complete workflow, MySQL service, locked installation, lint/type/test steps, migration/drift/seed/downgrade steps, frontend checks, and package changes. |
| Documentation | README, data-model ER/state diagrams, outline, decisions, review history, project status, testing plan, contribution rules, agent rules, PR template, and Section 3 checklist. |
| Design alignment | Relevant data/state and production-operation code in the local dashboard export; checked the support.js runtime entry and its role as design infrastructure. Original exports are references, not production authorization/security code. |

Frontend source has no Section 2 changes. This was a schema review, not a
complete visual/browser review of the prototype or a security audit of its
generated support runtime.

## Fresh verification results

Commands used the existing dedicated `prolog` conda environment. No Python,
dependency, database service, or base-environment installation was performed.

| Verification | Result |
| --- | --- |
| `python -m ruff check .` | Passed. |
| `python -m mypy app` | Passed, 19 source files. |
| `python -m pip check` | Passed. |
| `python -m pytest -q -p no:cacheprovider --cov=app --cov=scripts --cov-report=term-missing` | 43 passed. The initial sandbox run passed 41 and could not create temporary files for two tests; the authorized rerun passed all 43. |
| Scoped statement coverage | App: 100%; seed script: 95%; combined 255/256 statements, rounded to 99%. The remaining script statement is its `__main__` dispatch; CI executes the script entry point. |
| Actual migration on disposable SQLite | Upgrade/check, exact seeds, metadata comparison, additional constraint/FK probes, and populated downgrade passed. See probe details below. |
| Exact-head GitHub CI | All three jobs passed at `a91c6ee`; MySQL 8.4 upgrade/check/seed/downgrade steps explicitly succeeded. |

[CI run 34084236698](https://github.com/Larinx-JC/ProLog/actions/runs/34084236698)
also passed frontend lint, its scaffold test, TypeScript compilation, and
Vite build. These frontend checks were verified in CI, not rerun locally in
this review. The absent-project fallback steps were correctly skipped.

The additional local review probe used the actual Alembic environment and
migration, rather than `Base.metadata.create_all`. It checked:

- All column names, types, nullability, FKs, indexes, and nine named CHECKs
  against metadata, recording the server-default difference separately.
- Invalid ranges/deviation on both Material and Run; equality boundaries.
- Both invalid `pending_from` enum members and all allowed values including
  null; zero/negative intervals; end-time rejection and equality.
- Every declared FK, including review/record/audit actors; an arbitrary audit
  target ID remains allowed; deleting referenced parents is rejected.
- Exact role seeds and downgrade after inserting related synthetic rows.

The one-off probe and disposable databases are local review artifacts under
ignored `backend/coverage/`. They are not added to the permanent pytest suite
or claimed as MySQL behavioral coverage. Persistent MySQL behavior tests
remain assigned to Section 3 in the testing plan.

## Limits and accepted deferred work

- No local MySQL installation/service or Docker executable was available
  through the checks used here. MySQL evidence is the exact-head GitHub job.
  Local additional behavioral probes used SQLite and do not establish MySQL
  decimal, collation, timestamp, or concurrency behavior.
- UTC generation is correct. The current MySQL DDL uses plain `DATETIME`,
  with no fractional-second precision requested. MySQL defaults to zero
  fractional digits, so the SQLite `updated_at` test's 10ms delay does not
  establish that distinct subsecond updates remain distinct in MySQL.
  This is a precision/verification limitation, not a demonstrated violation
  of the agreed UTC policy. Decide/document precision before time-dependent
  services; do not use `updated_at` alone as a concurrency token.
  [MySQL fractional-second documentation](https://dev.mysql.com/doc/refman/8.4/en/fractional-seconds.html).
- Deterministic time tests, Windows CI, migrated-MySQL behavior tests, and
  action-runtime maintenance are already scheduled for Section 3.
- Snapshot copying/immutability, status-dependent review fields, calculations,
  atomic production/audit writes, and concurrency belong to the sole-writer
  services in Section 4. Their absence is not reopened as a Section 2 defect.
- Search indexes, export samples, fuller ingestion metadata, and deployment
  details remain with their approved owning sections.
- No schema, application code, migration, committed test, or CI behavior was
  changed during this review. Only the report and the owner's full-review
  workflow requirement are being recorded. Prototype files remain untouched.

## Before the next approval request

Resolve or explicitly disposition R2-01 and R2-02, review the resulting diff,
and attach fresh evidence for the final head. Then present the full review
result to the owner. Do not treat an approval of planning or a green run as
the owner's section-verification statement.

## Subsequent owner decision

On 2026-09-07, after this report was presented, the owner stated:

> Yes, I verify the production of Data Model & Database Schema and you can proceed to the production of Authentication & Multi-Level Authorization.

Section 2 is therefore verified. R2-01 and R2-02 remain visible follow-ups
to resolve and test during the authorized Section 3 work. The original review
verdict above is preserved as the record of what was presented for approval.

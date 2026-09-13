# Testing and verification

This plan covers implemented checks and future section work. See [project status](../PROJECT_STATUS.md)
for the last verified implementation commit.

## Current checks

| Check | Current evidence / scope |
| --- | --- |
| Backend lint and type checks | Ruff over backend files; mypy over `app`. |
| Backend pytest | Section 4 baseline: 284 passed. Section 5 adds HTTP lifecycle/authorization, strict numeric/settings validation, body limits, rollback, pagination/materialization and current-display tests; current counts are in its review. |
| SQLite constraints | Foreign keys enabled per test connection; structural CHECK rejection tests. |
| Windows/Linux backend CI | Locked dependencies, `pip check`, Ruff, mypy and the unit/SQLite migration suite on both systems. |
| Linux MySQL 8.4 CI | Upgrade/check/seeds/downgrade plus 22 Section 4 migrated behavior tests and two Section 5 HTTP tests. Covers auth races, lifecycle/concurrency/rollback, decimals, snapshots/display, constraints and migration parity. Match executed results to the section review's commit. |
| Frontend | ESLint, one scaffold component test, TypeScript compilation, and Vite build. |

The fast SQLite service/ORM fixtures create tables from metadata. A separate
SQLite migration test upgrades existing synthetic data and detects deliberate
default drift. MySQL tests run the actual migrations against the explicitly
designated disposable `prolog_test` database; they never use `create_all`.
See [the Section 5 review](reviews/section-05-review.md) for current executed
evidence and [the Section 3 review](reviews/section-03-review.md) for auth history.

Authentication fixtures use `tests.settings.SettingsWithoutDotenv` to ignore
developer dotenv files while retaining environment-variable loading and all
production validators. This avoids passing the runtime-only `_env_file` option
through Pydantic's editor-generated constructor signature. Targeted Pyright
verification of these files is recorded in the review; CI continues to use
Ruff/mypy plus runtime tests.

## Improvements and owners

| Due | Required addition | Acceptance evidence |
| --- | --- | --- |
| Section 3 — implemented | Windows/Linux units, separate Linux MySQL job, locked dependencies and `pip check`. | Exact-head results are recorded in the review. |
| Section 3 — implemented | App/script coverage excludes test-file execution. | Behavioral assertions cover success, rejection, expiry and persistence errors; percentage is supplementary. |
| Section 3 — implemented | Injectable auth clock; controlled timestamp-update test. | Before/at/after expiry and unchanged creation time assertions use no sleeps. |
| Section 3 — implemented | Migrated MySQL behavior tests. | Exact CHECK/FK error codes distinguish constraint rejection from unrelated database outages. |
| Sections 4–5 | Test each production transition, permissions, immutable snapshots, and concurrent writes through the services/APIs. | Invalid transitions and stale requests cannot leave a partial write or a misleading success audit event. |
| Sections 6–8 | Exercise query boundaries, permission filtering, export parsing, and ingestion deduplication. | Shared selection logic yields matching search/export data; malformed input and duplicate submissions have specified outcomes. |
| Sections 9–14 | Add browser walkthroughs and role checks as screens arrive. | New run → record → abnormality → close → Admin review → export works through the actual UI. |
| Sections 15–16 | Test installation, restart, local/VPN access, backup and restore. | A restored disposable instance reproduces representative data and its audit trail. |

GitHub supports operating-system job matrices; the Linux MySQL service job
can remain separate from the Windows unit job.
[GitHub matrix documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations)

## Test design rules

- Write an observable acceptance scenario before implementing important behavior.
  For a defect, add a regression that would fail with the defect present.
- Assert the result and relevant side effects: stored data, authorization,
  audit event, rollback, response, and time boundary.
- Use fixed input and controlled time for elapsed-time assertions. Repeating a
  timing test is useful diagnosis but does not prove it cannot be flaky.
  [pytest guidance](https://docs.pytest.org/en/stable/explanation/flaky.html)
- Keep fast isolated unit tests and targeted production-dialect integration
  tests. Directly test the critical CHECK expressions with invalid writes;
  `alembic check` shares autogenerate's detection limits and does not establish
  every constraint's meaning.
  [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- For MySQL integration, use only an explicitly designated disposable test
  database. Apply migrations rather than `Base.metadata.create_all` so tests
  exercise the shipped schema. Keep production credentials out of test jobs.
- Every important function has tests and documentation. A percentage alone is
  not acceptance evidence. State exclusions and separate unit, integration,
  browser, and deployment checks.
- After appropriate checks pass, repeat them only for changed behavior,
  failures, or unresolved concerns. Documentation-only changes need document
  and diff verification; the PR's existing CI can provide its normal checks.

## Local commands

From an Anaconda-enabled terminal, use the existing project environment:

```powershell
conda activate prolog
cd D:\Program\Projects\ProLog\backend
python -m ruff check .
python -m mypy app
python -m pytest -m 'not mysql' -q
python -m pip check
```

Check each command's exit code before proceeding. To request a scoped coverage
report, run `python -m pytest --cov=app --cov=scripts --cov-report=term-missing`.
This report is supplementary to behavioral acceptance tests.

The MySQL suite skips when `PROLOG_TEST_MYSQL_URL` is unset. It refuses any
driver/database other than `mysql+pymysql` / `prolog_test`, and deliberately
resets that test database. CI creates it in an isolated MySQL 8.4 container.
Run `python -m pytest tests/mysql -q` only against that disposable database.

From `frontend/`: `npm ci`, `npm run lint`, `npm test -- --run`, and
`npm run build`. Install only into project-specific environments.

## Evidence for handover

Record the tested commit, commands and exit status, important scenarios, CI
run URL, and anything unexecuted with its reason. A CI step that was skipped
or a run attached to an older commit is not evidence for the current change.
Check migration job steps directly; job duration does not demonstrate what ran.

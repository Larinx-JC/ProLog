# Testing and verification

This plan applies to future section work. The distinction between existing CI
and scheduled improvements is explicit below. See [project status](../PROJECT_STATUS.md)
for the last verified implementation commit.

## Current checks

| Check | Current evidence / scope |
| --- | --- |
| Backend lint and type checks | Ruff over backend files; mypy over `app`. |
| Backend pytest | 43 tests at `e98da3f`, including SQLite ORM behavior, seed-verifier branches, and UTC assertions. |
| SQLite constraints | Foreign keys enabled per test connection; structural CHECK rejection tests. |
| Linux MySQL 8.4 CI | Alembic upgrade, `alembic check`, seeded codes/names/descriptions verification, and downgrade. |
| Frontend | ESLint, one scaffold component test, TypeScript compilation, and Vite build. |

The SQLite ORM suite currently creates tables from metadata. The MySQL CI
steps validate the migration and seeds but do not yet run the ORM behavior
suite against the migrated MySQL schema.

## Improvements and owners

| Due | Required addition | Acceptance evidence |
| --- | --- | --- |
| Section 3 | Run backend unit tests on Windows and Linux with the locked dependencies. Keep the MySQL service job on Linux. | Both operating-system runs pass for the current PR head; include `pip check`. |
| Section 3 | Separate app/script coverage from test-file execution and report behavior assertions. | Important success, rejection, and error branches are tested; coverage commands name their source scope. |
| Section 3 | Use an injectable clock for session/invitation expiration tests; remove the existing sleep dependency in the update-timestamp test. | Before/at/after expiry cases are deterministic; `created_at` stays fixed and `updated_at` changes after a write. |
| Section 3 | Add behavior tests using a disposable, migrated MySQL schema. | Decimal round trips, invalid FKs/rules, seed content, auth session storage, invitation races, and transaction rollback have real database assertions. |
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
python -m pytest -q
python -m pip check
```

Check each command's exit code before proceeding. To request a scoped coverage
report, run `python -m pytest --cov=app --cov=scripts --cov-report=term-missing`.
This report is supplementary to behavioral acceptance tests.

From `frontend/`: `npm ci`, `npm run lint`, `npm test -- --run`, and
`npm run build`. Install only into project-specific environments.

## Evidence for handover

Record the tested commit, commands and exit status, important scenarios, CI
run URL, and anything unexecuted with its reason. A CI step that was skipped
or a run attached to an older commit is not evidence for the current change.
Check migration job steps directly; job duration does not demonstrate what ran.

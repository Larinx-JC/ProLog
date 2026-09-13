# Full Sections 3 and 4 review — 2026-09-13

Result: **two confirmed medium-severity bugs**, both involving migration paths.
No additional authentication bypass or production-lifecycle defect was found
in the reviewed implementation. The findings below are still open; this review
does not withdraw the owner's historical Section 3 approval or approve Section 4.

## Reviewed scope

- Section 3: the complete change from Section 2 `6b0509e` to `f7bee48`.
- Section 4: the complete change from `f7bee48` through
  `4899d5e9d61490922c88314ddfb51301d439d6b0`, including the current uncommitted
  display-settings amendment and its new migration/tests.
- Checked implementation, database changes, test assertions, CI/dependencies,
  documentation and confirmed decisions D14–D30. Earlier green checks and
  previous review reports were supporting evidence, not a substitute for this review.
- Backend Python snapshot SHA-256:
  `b50b81cbee8caac1be5c8a31f212b3a2adc2c50d852fd6107444f387f3836f42`.
  This hashes the 80 `.py` files in `backend/app`, `alembic`, `tests`, and
  `scripts`, sorted by backend-relative POSIX path, concatenating each path,
  a null byte, raw file bytes, and another null byte.

## R34-01 — Medium: an older Admin identifier can defeat local recovery

Locations: [recovery lookup](../../backend/app/services/users.py#L139),
[new account normalization](../../backend/app/core/security.py#L78), and
[authentication migration backfill](../../backend/alembic/versions/7a9b31c4d502_authentication.py#L23).

Section 2 allowed account identifiers such as `ab`; its database has no
three-character minimum or ASCII account-format constraint. Section 3 preserves
that identifier and marks bootstrap complete when the existing Admin is found.
However, both login and local recovery pass it through the new, stricter
normalizer. Login fails, local recovery rejects the identifier, and creating a
replacement first Admin is prohibited. A valid stored password does not help.

Reproduced against an isolated database using the actual migrations:

1. Upgrade to `0c3dff882627` and insert the sole Admin with account `ab` and a
   valid Argon2 hash for a synthetic known password.
2. Upgrade to current `head`; the upgrade succeeds and preserves the account.
3. Login with that account/password returns `invalid_credentials`.
4. `recover_admin("ab", replacement)` raises the account-format `ValueError`.
5. Bootstrap of `replacement.admin` returns `bootstrap_already_completed`.

Impact is conditional on importing/upgrading pre-authentication accounts that
do not meet the new identifier policy. Accounts created through Section 3's
normal provisioning are unaffected. No real user database was inspected.

Recommended correction: provide an explicit, audited local remediation path
that can select the existing account by stable ID and assign a validated,
collision-checked canonical identifier. Add an upgrade/preflight check so an
incompatible sole Admin is not silently left inaccessible. Keep the agreed
normal identifier rules and final-Admin protection. Do not silently rename
accounts or rewrite the already merged migration.

Regression evidence should include incompatible legacy identifiers, naming
collisions, successful recovery and subsequent login, and unchanged role,
ownership and audit references. Existing migration tests only use a compatible
`existing.admin` identifier, so they do not catch this case.

## R34-02 — Medium: offline upgrade SQL seeds a null required timestamp

Locations: [display seed execution](../../backend/alembic/versions/c2a54f8d7109_display_settings.py#L51)
and [non-null timestamp column](../../backend/alembic/versions/c2a54f8d7109_display_settings.py#L38).

The migration supplies `now` as an execution parameter while the SQL expression's
typed bind parameter has no value. Online migration receives that execution
parameter. Alembic's offline MySQL SQL generation instead renders the unbound
value as `NULL`.

Reproduced `command.upgrade(Config("alembic.ini"), "head", sql=True)` with a
synthetic MySQL URL, without opening a MySQL connection. The generated seed has:

```sql
INSERT INTO display_settings (..., rounding, updated_at)
SELECT 1, ..., a.rounding, NULL
FROM production_settings s
JOIN accuracy_versions a ON a.id = s.accuracy_version_id
WHERE s.id = 1;
```

The migration creates `updated_at` as `NOT NULL`, without a server default.
Thus the generated SQL does not satisfy its own schema, although SQL generation
exits successfully. This affects applying a generated upgrade script; it does
not invalidate the passing online SQLite migration tests. The generated script
was inspected, not executed against a live MySQL instance during this review.

Recommended correction: bind the UTC timestamp value into the typed SQL
expression before execution, so both online and literal/offline compilation
receive it. Add a MySQL-dialect offline-generation regression asserting a
non-null timestamp, and retain the populated online migration checks. This
display revision is uncommitted, so its correction need not alter approved history.

## Coverage of the full review

| Area | Reviewed behavior and conclusion |
| --- | --- |
| Authentication primitives and configuration | Password hashing/rehashing and bounds, opaque tokens/digests, CSRF binding, allowed origins, production cookie/secret configuration and safe public errors. No new credential-disclosure or authorization-bypass finding. |
| Account and session services | Invitations, activation/recovery single use and expiry, current roles, forced password change, idle/absolute expiry, background-read behavior, revocation, rate counters, local administration, final-Admin protection and atomic audit writes. Legacy identifier recovery has R34-01. |
| Production services and authority | Ownership and current account checks occur inside the shared transaction. Examined start/record/correct/close/review, state and resolution matrices, missing-data exceptions, sticky abnormality, self-review evidence, revisions, durable retries and audit rollback. No new lifecycle finding. |
| Calculations, precision and time | Complete rule snapshots, target-based alarms before result rounding, independent limits, separate uniformity, zero/null handling, captured precision, optional/required readings, UTC/Shanghai normalization, scheduled versus manual samples and closure counts. |
| Current display amendment | Shared formatting and per-field mappings; Admin-only updates; current preferences for existing/new runs; canonical edit values and original alarms/audits preserved; retry receipts remain canonical. No additional display-service finding; migration SQL generation has R34-02. |
| Persistence and migrations | Auth backfill/seeds, FK/CHECK/default parity, precision widening, legacy policy, timestamp precision, display seed, populated preservation, numeric downgrade guard and MySQL FK-index rollback handling. Reviewed online and offline paths separately. |
| Tests and CI | Read behavioral assertions, fixtures and migration/race tests, rather than relying on statement coverage. SQLite FKs are enabled in behavior tests. MySQL races use separate connections. The two reproduced paths need regression tests; current display MySQL execution remains pending. |
| Documentation and scope | Compared the auth/lifecycle/settings contracts and acceptance checklists with D14–D30. Production endpoints, UI, search/export/ingestion and deployment remain assigned to their later sections. Historical Section 3 counts and limits are not evidence for new display changes. |

## Executed verification

Used only `D:\Program\Environment\Anaconda3\envs\prolog\python.exe`.
No dependencies or Python installations were added.

| Check | Observed result |
| --- | --- |
| Full local backend suite, excluding MySQL | **283 passed; 22 deselected**. Includes real SQLite migration upgrade/drift/downgrade tests. |
| Scoped app/scripts coverage | **1,687/1,689 statements**; two module-dispatch statements remain outside this suite. Passing coverage did not detect the two findings. |
| Ruff | Passed. |
| mypy | Passed; 44 app source files. |
| `pip check` | Passed in the existing conda environment. |
| Frontend ESLint, Vitest, TypeScript and Vite build | Passed; one scaffold component test. |
| Additional migration probes | Reproduced both findings using synthetic credentials and disposable files under ignored `backend/coverage/`. |
| Git whitespace validation | Passed. |

Backend command, from `backend/`:

```text
python -m pytest -m "not mysql" --cov=app --cov=scripts --cov-report=term-missing -p no:cacheprovider --basetemp coverage/review-03-04 --tb=short
```

The GitHub run list was queried during this review. It confirms successful
[CI 34570576438](https://github.com/Larinx-JC/ProLog/actions/runs/34570576438)
for exact head `4899d5e9d61490922c88314ddfb51301d439d6b0` and successful
[CI 34567271585](https://github.com/Larinx-JC/ProLog/actions/runs/34567271585)
for `f3441973a89710a2f37c7affe0b53a1fa85f2874`. The previous review records the
latter's 19 MySQL tests. Neither run includes the uncommitted display amendment.
No new MySQL run or CI execution is claimed for the reviewed working tree.

## Remaining limits and handover

- Run the complete MySQL 8.4 suite and Windows/Linux CI for the actual corrected
  display-amendment commit before Section 4 verification. The current suite
  contains 22 MySQL cases; this review did not run a local MySQL service.
- The shared coordination lock serializes reads/writes; `get_run()` currently
  materializes all measurements. Public response bounds, query indexes and
  representative load tests remain the documented Sections 5–6/8 follow-ups.
- API/CLI tests are not a real-browser or deployed HTTPS/VPN test. Production
  endpoints, auth/production screens, instrument input, exports and deployment
  testing retain their agreed later-section ownership.
- Findings were reproduced and documented, not fixed in application code.
  This review changes only review/status documentation and ignored probe/test
  artifacts. Existing working changes and `prototype/` were preserved.
- No commit, push, merge or section advancement was performed during this review.

Address R34-01/R34-02, review the affected corrections and rerun their relevant
checks before presenting the next Section 4 verification request.

## Owner approval and correction follow-up — 2026-09-13

After receiving these findings, the owner stated: "ok, I approve the
implementation for 4 and lets start section 5". This authorizes Section 5;
the original findings above remain the historical review result.

R34-02 is corrected in the unmerged display migration: the UTC datetime is
bound as a typed expression value, so offline compilation and online execution
receive the same value. A new regression generates the entire MySQL upgrade
script and asserts the display seed contains a timestamp literal rather than
NULL. The affected correction was reviewed; current verification is recorded
in project status and PR #4 before merge.

R34-01 remains open. Track an audited local legacy-identifier remediation and
preflight procedure before upgrading a database containing incompatible old
accounts, and no later than Section 15 deployment. New accounts use the
validated canonical format. Owner approval is not recorded as fixing this issue.

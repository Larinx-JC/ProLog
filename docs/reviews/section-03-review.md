# Full Section 3 review

Reviewed on 2026-09-07. Result: no remaining blocking finding in the authorized
authentication section after the corrections below. Ready for owner
verification; PR #3 remains draft and unmerged. Section 4 is not authorized.

## Scope and method

- Base: merged Section 2 `6b0509e`.
- Reviewed implementation head: `8a44eb4c284986cf5b31c48ac276cdc770668681`.
- [PR #3](https://github.com/Larinx-JC/ProLog/pull/3).
- Compared the entire section diff against its base, then reviewed the affected
  corrections and final documentation. This was an implementation-agent review,
  not an independent security assessment.
- Checked the owner's decisions D14–D18 and every AUTH-01–AUTH-16 criterion.
  The [acceptance evidence map](../sections/03-authentication.md) names the tests.

The full review included these areas, not just the most recent CI fix:

| Area | Reviewed evidence and conclusion |
| --- | --- |
| Security primitives/configuration | Argon2id parameters, input bounds and normalization, unknown/pending credential handling, random tokens and persisted digests, CSRF HMAC binding, production secret/HTTPS/cookie checks. No raw password/token appears in public account results or audit values. |
| Persistence/migrations | All four auth tables, activated-user backfill, singleton coordination seed, indexes/FKs/CHECKs, upgrade/downgrade, ORM defaults and historical migration. AST comparison confirms the initial migration's executable operations are unchanged; it gained two docstrings. |
| Service boundaries | AuthService coordinates UserService, SessionService and InvitationService. Current authority is rechecked within account-mutation transactions. MySQL coordination serializes grants, bootstrap, revocation and final-Admin checks. Failure counters commit only on explicitly marked safe rejection paths. |
| Roles and account lifecycle | Admin full authority, Operator all-run visibility and own-run edit capability, Reviewer read/export only. Final active Admin protection, activation/recovery eligibility, reissue, forced change, disable/demotion and multi-session revocation match confirmed policy. Production edit-state checks remain Section 4. |
| API and CLI | Reviewed every auth route, JSON schemas, cookie transport, CSRF/origin restrictions, safe error handlers, cache/referrer headers, CLI bootstrap/recovery and password prompts. API/CLI tests exercise actual handlers with synthetic users. |
| Tests and isolation | Reviewed assertions for successful and rejected behavior, expiry boundaries, stale credentials, transaction rollback, role bypass, races and migrated data. SQLite FKs are enabled; MySQL tests use actual revisions and refuse a non-designated database. |
| Dependencies/CI | Argon2 additions are pinned in the backend lock. Windows/Linux units use the same lock and include pip check. Linux MySQL runs migration/default/seed checks and behavior tests. Frontend lint/test/build remains mandatory. |
| Documentation/scope | Reviewed status, README, decisions, contributing rules, implementation brief, acceptance checklist, testing plan, data-model link and authentication operations/types/class/data-flow documentation. Prototype files and later section implementation were left untouched. |

## Findings and corrections

| ID / severity | Finding | Correction and verification |
| --- | --- | --- |
| R3-01 / Medium | Standard argparse errors could echo a password mistakenly provided as an unsupported argument. | SafeArgumentParser displays usage without submitted argument values. The CLI rejection test checks stdout and stderr for the synthetic secret. Fixed in `382d0b2`. |
| R3-02 / Medium | Migration preservation was initially demonstrated on SQLite without equivalent populated MySQL evidence. | Added MySQL upgrade with an existing Admin, exact field/seed checks, repeat-bootstrap rejection, local recovery/login and downgrade preservation. Also tested both activation and recovery consumption races. |
| R3-03 / High, CI blocker | Enabling default comparison exposed MySQL's numeric Boolean reflection versus ORM true/false expressions. Initial CI `34157400883` failed drift checking. | Numeric SQL 0/1 metadata defaults match MySQL without disabling comparison. A deliberate changed default still produces a drift finding on both dialects. Corrected in `50c9245`, verified in the final green run. |
| R3-04 / Medium, test defect | PyMySQL reports CHECK rejection as OperationalError/3819, so tests expecting SQLite's IntegrityError failed despite correct constraints. | Assert DBAPI error codes 3819 (CHECK) and 1452 (FK), preventing unrelated outages from passing. Corrected in `8a44eb4`; all eight MySQL tests passed. |
| R3-05 / Medium, acceptance gaps | Initial tests did not explicitly prove API logout-cookie removal/replay, forced-change route restrictions, Admin/CSRF background reads, grant/address throttles or rollback after activation flush. | Added assertions through the actual API and services, including retry after a failed activation audit. Final local and both operating-system suites passed all 129 tests. |
| R2-01 / inherited Medium | Approved Section 2 ORM metadata omitted 12 migration server defaults, and drift comparison ignored defaults. | Metadata parity and default comparison are enabled. Both actual migrations and intentional-drift regressions pass. |
| R2-02 / inherited Low | Some model/debug, migration and seed-entry functions lacked docstrings. | Added function documentation. An AST check found no undocumented functions in app/scripts; migration functions are documented as well. |

## Verification evidence

[CI run 34159260847](https://github.com/Larinx-JC/ProLog/actions/runs/34159260847)
passed for the exact implementation head `8a44eb4`. Job and step records, plus
test-count log lines, were read directly; execution was not inferred from duration.

| Check | Result |
| --- | --- |
| Local `python -m ruff check .` | Passed. |
| Local `python -m mypy app` | Passed, 30 source files. |
| Local `python -m pip check` | Passed in existing Anaconda `prolog`; no base/standalone Python installation. |
| Local `python -m pytest -m 'not mysql' --cov=app --cov=scripts --cov-report=term-missing -p no:cacheprovider --tb=short` | 129 passed, eight MySQL tests deliberately deselected. |
| Scoped statement coverage | 924/926 app/script statements. Two unexecuted unit-suite lines are CLI/script `__main__` dispatch; important functions have direct tests. Coverage is supplementary to behavior assertions. |
| Local frontend lint / Vitest / TypeScript + Vite build | Passed; one scaffold component test. Frontend implementation is unchanged in this section. |
| Windows and Linux backend CI | 129 passed on each; locked install, pip check, Ruff and mypy passed. |
| MySQL 8.4 CI | Eight tests passed; upgrade, seeds, default-aware drift check and final downgrade all explicitly succeeded. |
| MySQL behavior | One successful concurrent bootstrap/activation/recovery; final-Admin preservation; failed audit rollback; existing-user migration preservation; decimal round-trip, constraint/FK rejection, microsecond persistence and deliberate default drift. |
| Document/diff checks | UTF-8 decoding, relative file links, YAML parsing, function documentation, historical migration AST parity and Git whitespace checks passed. The handover documentation was reviewed after the code fixes. |

The API/CLI demonstration procedure is in [authentication operations](../authentication.md).
It uses test clients and disposable synthetic accounts, including activation,
role rejection, password recovery, revocation and expiry. It does not require
creating a real account or exposing the local database.

## Remaining limits and assigned follow-ups

- Section 9 owns browser login/activation/recovery/account screens and real
  browser cookie/CSRF walkthroughs. Returned links target that future UI;
  Section 3 demonstrates consumption through the API. No browser UI is claimed.
- Sections 4–5 must use the production services as the sole writers, recheck
  current authority within writes, and enforce lifecycle eligibility. Detached
  Identity/route checks alone are insufficient for concurrent production changes.
  Self-review, factory timezone and decimal rounding remain explicitly unresolved.
- Section 15 must verify Windows service startup, HTTPS/reverse-proxy trust,
  VPN/firewall topology, retention/cleanup of expired auth records and backups,
  restore behavior and logging. No live deployment or local MySQL service was
  installed or exercised in this review; MySQL evidence is from CI.
- The shared authentication row lock is a documented throughput tradeoff for
  the factory workload. MySQL race tests use independent connections and threads;
  they are not a production load test or a full multi-process deployment test.
  Benchmark expected client/worker counts before deployment.
- No external penetration test or availability guarantee is claimed. The section
  provides tested backend authentication controls for the agreed local/VPN design.

## Approval boundary

The owner has approved Section 2 and authorized this section only. Passing
tests and this review do not merge PR #3 or authorize Section 4. The owner must
verify Authentication & Multi-Level Authorization before the next section begins.

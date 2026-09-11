# Full Section 4 review

Reviewed on 2026-09-11 against Section 3 base
`f7bee48d5fc8d43f83fc774c28e753421f7f3aef`. The review covers the entire section,
including the acceptance plan in `28bf736`, implementation in `4b2ce8a`, MySQL
correction in `63dc7b6`, and final follow-up implementation `f344197`.

Result: no remaining blocking finding in the authorized domain-service scope.
Final implementation CI passed all five jobs. Section 4 awaits owner verification;
PR #4 remains draft and unmerged. Section 5 has not been authorized.

## Scope and method

Inspected the complete diff and resulting source, not only recent corrections:

- All pure numeric, measurement and sampling policies, and every production
  service, including shared transactions, current authorization, retry receipts,
  optimistic revisions and audit payloads.
- ORM changes, the new migration in both directions, populated preservation,
  legacy interpretation, timestamp and numeric capacity, and MySQL test cleanup.
- Every new test and fixture, existing CI commands/jobs, dependency pin/lock,
  existing authentication interactions, and Section 3 closeout documentation.
- Owner decisions D19–D29, all DOMAIN-01–15 acceptance criteria, numerical
  examples, workflow/data flow, class relationships, section boundaries and
  the added Admin settings page plan. Local prototype files remain unchanged.

Executed the local suite in the dedicated `prolog` conda environment. Inspected
the actual GitHub job/step results for the named commits. MySQL findings were
confirmed against the CI MySQL 8.4 container, not inferred from SQLite success
or job duration. Follow-up tests use real services and controlled clocks.

## Findings and corrections

| ID | Severity | Evidence and correction | Verification |
| --- | --- | --- | --- |
| R4-01 | High, fixed | Downgrade at `4b2ce8a` failed because InnoDB used `uq_measurement_run_slot` to support `Measurement.run_id`'s foreign key. Restore a supporting `run_id` index before dropping the composite index. Keep the numeric-loss guard and FK enforcement. | Failure in CI `34562519821`; corrected `63dc7b6` passes MySQL populated upgrade/check/downgrade and all five CI jobs in `34563625649`. |
| R4-02 | Medium, fixed | A legacy run read retroactively counted missed samples using Section 4's new schedule. Return null completeness and an explicit unavailable-schedule error for legacy policy; retain stored history and read-only protection. | `test_legacy_history_does_not_invent_missed_samples`; existing populated migration verifies original statistics and policy backfill. |
| R4-03 | Medium, fixed | The combined close/review race could skip double-review coverage when review won after closure. Split it into separate tests. Also race actual corrections of an existing measurement and assert one correction/audit survives. | Dedicated MySQL double-review and measurement-correction tests, with independent transactions and explicit conflict outcomes. |
| R4-04 | Medium, fixed during implementation | Assigning an unchanged `updated_at` instant could leave SQLAlchemy free to apply its real-clock onupdate default. The next controlled-time write then failed chronology validation. Force the service timestamp dirty with shared `stamp_update`. | Same-instant/late-recording regression; MySQL verifies microsecond run, measurement and audit timestamps after a fresh read. |
| R4-05 | Low, fixed | Planning text still described rounding/completeness as unresolved, and the Measurement docstring tied all statistics to complete rows. Align docs with confirmed choices and calculation once four points exist. | Full documentation cross-check; partial/completion and formula tests. |

The MySQL behavior underlying R4-01 is documented in the
[MySQL foreign-key restrictions](https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html):
InnoDB may replace an implicitly created supporting index when another suitable
index is added. The fix preserves support throughout downgrade.

## Acceptance evidence

| Criteria | Reviewed behavior and tests |
| --- | --- |
| DOMAIN-01/02/13 | Decimal strings, 0–6 scales, halfway rounding, storage overflow, exact unrounded target comparisons, independent enabled limits, partial alarms, zero/undefined uniformity, Shanghai/UTC normalization and slot/date boundaries. `test_numeric_policy`, `test_production_calculations`, `test_sampling_policy`, plus MySQL six-place/timestamp readback. |
| DOMAIN-03/04 | Admin material management, positive target/coherent ranges, soft deactivation, complete immutable rule copy, policy capture and unchanged old-run evaluation after material edits. Material-edit/start and policy-edit/start MySQL races reject mixed snapshots. |
| DOMAIN-05/06/07 | Current role/ownership checks; Operator Abnormal-work switch tested for both save and close; sticky alarms; required-field gaps; scheduled versus extra samples; Admin-only exception reason; closed/Reviewed immutability. |
| DOMAIN-08 | Active/Abnormal source × every valid/invalid resolution; Admin-only review; blank-reason rejection; self-review of prior contributions; contradictory pending metadata rejected; audit keeps original gap and reason. |
| DOMAIN-09/10/11/12 | Data/audit/receipt rollback on injected database failure; durable create/close/review retries without duplicate events; stale revisions; MySQL duplicate requests, correction/close/review races and account-disable races; idle monitoring does not renew sessions. |
| DOMAIN-14 | New revision after the approved migrations; original numeric/uniformity data and auth records survive; legacy policy marked explicitly; precision-loss downgrade refuses before dropping schema; exact role seeds, model parity and actual MySQL migration cycles. |
| DOMAIN-15 | Function docstrings, shared service/value classes, workflow and class diagrams, documented types, executable synthetic lifecycle demonstrations, full diff review and recorded section gate. |

## Verification record

- Local backend on 2026-09-11: **254 passed**, 19 MySQL tests deselected. Ruff,
  mypy (42 app source files) and `pip check` passed in the existing `prolog`
  environment. Coverage of `app` plus `scripts`: 1,611/1,613 statements; the
  uncovered statements are the two CLI/script module-dispatch lines. Statement
  coverage alone does not establish branch or production-environment correctness.
  AST inspection found no undocumented functions in changed Python files;
  relative documentation links and `git diff --check` passed.
- Frontend regression on 2026-09-11: ESLint, one Vitest test, TypeScript and Vite
  production build passed. Section 4 changes no frontend implementation.
- MySQL correction baseline: all five jobs passed for `63dc7b6` in
  [CI 34563625649](https://github.com/Larinx-JC/ProLog/actions/runs/34563625649),
  including migrate/seed, persistence/race/rollback tests and final drift/downgrade.
- Final implementation commit: `f3441973a89710a2f37c7affe0b53a1fa85f2874`.
  [CI 34567271585](https://github.com/Larinx-JC/ProLog/actions/runs/34567271585)
  passed all five jobs. Actual logs confirm 254 passed/19 deselected on each
  Windows/Linux unit runner and **19 passed** in MySQL (none skipped), plus
  seed, drift, downgrade and frontend checks. Subsequent handover changes only
  update documentation; the PR records checks for that documentation head.

## Limits and follow-up obligations

- This delivers backend domain services. Production HTTP contracts, request
  validation, CSRF integration and bounded response sizes are Section 5.
  Admin settings UI is Section 11D; operational UI and refresh behavior remain
  in Sections 10–13. No end-to-end browser factory workflow is claimed.
- Legacy rows remain readable but cannot be edited, closed or reinterpreted by
  new writers without an explicit conversion policy. New scheduled completeness
  cannot be reconstructed for them. Migration does not import prototype data.
- The common AuthState lock serializes authentication and production work,
  including reads. `get_run` currently loads all readings for one run. Section 6
  must add query bounds/indexes and representative-volume benchmarks; Section 8
  must assess throughput before machine intake. No production-scale claim is made.
- Accuracy-version immutability and lifecycle writers are service-enforced.
  Later APIs/importers must reuse these writers. Direct administrative SQL can
  bypass business invariants; no database trigger-based enforcement is claimed.
- Production receipts persist indefinitely. Retention, backup/restore and
  deployment administration need definition in Section 15. A permitted downgrade
  deletes Section 4 metadata and narrows timestamps; it is not an archive tool.
- MySQL was tested in disposable CI, not an installed local factory service.
  Physical instruments, real production datasets, Windows service deployment,
  export layouts and machine ingestion remain unverified in this section.

## Approval boundary

Only the owner's explicit verification can approve Section 4 and authorize
Section 5. Passing this review or CI does not merge PR #4 or advance the project.

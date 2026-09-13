# Section 5 full review — Backend API Layer

Review date: 2026-09-13. Section 4 was approved by the owner and merged as
`8e297e9`; this is the complete Section 5 diff base. Branch:
`codex/section-05-backend-api`. Owner Section 5 verification is pending.

## Scope and method

Reviewed every new/changed section file against the base: HTTP routes, request
and response schemas, middleware, read service, app registration/error handling,
test harness, API/read/transport tests, MySQL HTTP integration tests, acceptance
plan, API documentation and status/review updates. Also traced the unchanged
authentication transaction, session/permission checks, production writers,
serializers, captured accuracy and display formatting which the routes call.
No migration, dependency or frontend code changed. The untracked prototype is
owner material and is excluded from the diff.

The review compared the implementation to decisions D14–D30 and API-01–API-12.
It checked data flow and adverse cases, rather than treating coverage as proof
of behavior. The same implementation agent performed this review; it is not an
independent external audit.

## Findings and corrections

| ID / severity | Evidence and consequence | Disposition |
| --- | --- | --- |
| S05-01 / Medium | MySQL pads material DECIMAL values to six places. Returning these unchanged for edit forms would make an otherwise unchanged rule set fail the current two/three-place recording validator. Rounding to current precision would lose archived significant digits. | Corrected in `ProductionReadService`: strip padding zeros only. Tests assert exact values and HTTP GET→PUT roundtrip, including inactive material precision after a settings decrease. |
| S05-02 / Low | Reusing the full RunStatus enum for response `pending_from` would advertise two impossible pending-source values in OpenAPI. | Corrected to the two allowed literals plus null; OpenAPI enum assertion added. Database constraints and service transitions are unchanged. |
| R34-01 / Medium, inherited | A pre-authentication legacy Admin with an incompatible identifier can be preserved by migration but cannot use canonical login/recovery. | Still open. Requires an audited local remediation/preflight before upgrading an affected legacy database and before Section 15 deployment. Newly provisioned canonical accounts are unaffected. Section 4 approval did not erase this finding. |

No remaining production-blocking defect was found in the Section 5 change.
The inherited legacy-upgrade limitation must remain explicit. Current Section 5
MySQL verification is pending until the PR's exact-commit CI runs.

## Acceptance evidence

| Requirement | Direct evidence |
| --- | --- |
| API-01 lifecycle | Real HTTP create/sample/correct/close/self-review, partial missing closure exception, sticky abnormal state and terminal rejection tests. |
| API-02–03 authority | All ten GET routes reject missing sessions; all nine writes reject a valid pre-auth CSRF cookie. Role tests include direct Admin-route and cross-owner correction attempts. Polling does not extend the 30-minute idle boundary; forced-change and revoked sessions reject. |
| API-03 browser proof | Missing/wrong CSRF, untrusted Origin and non-JSON write rejection, plus no production side effect. |
| API-04 numbers/limits | Reject JSON floats/booleans, excess digits, NaN, forged identity/calculations and invalid/incomplete policy bodies. Full-app oversized JSON rejection; ASGI declared/streamed/dishonest-length boundary and disconnect tests. |
| API-05 transactions | Stable retries, conflicting payloads, stale revisions, cross-parent rejection and injected audit-insert failure returning safe 503 with full database rollback. |
| API-06 bounded reads | Observe ORM load events: a 205-sample run detail loads zero sample rows, then pages load only 200 and five. Stable time/ID ordering, total/empty-page boundaries, parent isolation and page parameter rejection. |
| API-07 precision/display | Canonical three-place resistance remains exact while current display changes; alarms persist. Material edit roundtrip and inactive older precision are checked. Legacy completeness remains unknown instead of fabricated. |
| API-08 audit | Admin/Reviewer read permission, Operator rejection, original payload text comparison and session-token absence. Explicit response fields; no mutation route. |
| API-09 overview | Empty database and UTC 15:59:59→16:00:00 Shanghai day boundary. Today's starts and all-time current statuses remain separate, with stable recent-run order. |
| API-10 contract/errors | OpenAPI decimal-string/required-field/extra-field/pending-source assertions. Domain/database/schema error mapping and no-cache headers; response models enumerate public fields. |
| API-11 MySQL | Two new migrated-database HTTP tests: six-place readback, unrounded alarm result, Admin review/Reviewer denial; independent HTTP clients racing the same revision produce one winner. Execution evidence to be recorded below. |
| API-12 handover | Full diff review, [API guide](../backend-api.md), [plan](../sections/05-backend-api.md), project status and PR preparation. |

## Verification

Local checks use only the existing `prolog` Anaconda environment. After all review
corrections, **353 tests passed**, with 24 MySQL tests deselected. Ruff, mypy
(48 source files), `pip check` and staged Git diff checks pass. App/script coverage
is 2,138/2,140 statements; the same two pre-existing module-dispatch lines are
uncovered. The 69 new local cases include 43 HTTP, 20 read-service and six
transport tests. Exact-commit MySQL/Windows/Linux CI evidence is pending below.

Section 4 closeout is separately proven at `df8ec69` by
[CI 34743260352](https://github.com/Larinx-JC/ProLog/actions/runs/34743260352):
284 backend tests on Windows and Linux, 22 MySQL tests and all five jobs passed.
This baseline evidence is not substituted for Section 5 CI.

## Limits and next boundary

- MySQL runs in disposable GitHub CI; no local factory database was modified.
- The shared AuthState transaction lock prioritizes consistent authority and
  atomic writes. Collection counts, per-run policy lookups and large offsets
  still require Section 6 benchmarks/index choices on representative volume;
  bounded materialization is not a throughput guarantee.
- Offset pages can shift between requests during concurrent writes; no stable
  export/search snapshot is claimed. Section 6 owns selection semantics.
- No browser screens, exports, machine portal, production deployment, factory
  walkthrough or independent security audit is included in this section.
- Section 6 requires owner verification of Section 5 plus its scheduled search
  decisions. Passing CI does not authorize advancement or merging on its own.

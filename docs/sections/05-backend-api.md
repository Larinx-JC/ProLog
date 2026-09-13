# Section 5 — Backend API Layer

Authorized by the owner on 2026-09-13: "ok, I approve the implementation for 4
and lets start section 5". This section exposes the approved domain behavior;
Section 6 remains responsible for advanced search and query benchmarks.

## API and class outline

- `/production/runs`: bounded listing, creation, detail, measurement pages,
  scheduled-sample pages, corrections, closure and Admin review.
- `/production/materials`: bounded listing/detail and Admin create/update,
  including activation state, exact rules and current display copies.
- `/production/settings/accuracy` and `/production/settings/display`: current
  settings and Admin updates with required reason, request UUID and revision.
- `/production/audit-logs`: bounded Admin/Reviewer reads; Operators denied.
- `/production/overview`: explicit current status counts, today's run-start
  count using Asia/Shanghai, and recent run summaries. Completion/quality KPI
  semantics remain a Section 10 choice; no speculative rate is introduced.

HTTP routers and typed schemas delegate all writes to Section 4 services.
A shared read service performs bounded database queries under current authority,
returns detached documents and reuses the existing canonical/display serializers.
Reads do not renew idle sessions. Run details do not embed an unlimited array
of measurements; the separate measurement endpoint is paginated.

Use the existing HttpOnly session cookie and JSON/Origin/CSRF requirements.
Request bodies reject unknown properties, binary-float numeric inputs and
coerced booleans/integers. Decimal strings retain their original fractional
digits until the captured domain precision policy validates them. Each write
requires a UUID request ID; updates require optimistic revisions and applicable
reasons. Response documents expose only explicit public fields. Domain errors
map to stable HTTP errors without echoing request data or SQL.

Initial technical bounds: pages default to 50 and permit at most 200 items;
positive IDs and revisions fit signed MySQL integers; maximum JSON request
body is 64 KiB, including streamed bodies. Lists use stable ordering and expose
offset, limit, total and a has-more flag. General attribute/date search is
Section 6; these are basic navigable collections and parent-scoped reads.

## Acceptance checklist

| ID | Required evidence |
| --- | --- |
| API-01 | Real HTTP lifecycle: start, partial/complete sample, correction, close and reasoned Admin review. |
| API-02 | Every production route requires current permitted authentication; direct Operator/Reviewer writes cannot bypass role/ownership/state rules. |
| API-03 | Mutations require trusted Origin, CSRF proof and JSON; revoked/expired/forced-change sessions fail; GET polling cannot renew idle time. |
| API-04 | Decimal strings survive transport exactly; numeric JSON values, excess places, forged computed/identity fields, wrong types and oversized bodies are rejected. |
| API-05 | UUID retries return stable canonical results without duplicate data/audits; stale revisions and conflicting retries return 409; domain failures retain atomic rollback. |
| API-06 | Run detail, collection and measurement responses are bounded; database queries limit materialization and have stable ordering. Parent IDs cannot expose unrelated measurements. |
| API-07 | Display reads use one current preference revision while canonical values and captured accuracy remain intact. Inactive materials with older precision retain exact rules. |
| API-08 | Admin/Reviewer audit reads omit credentials and preserve original before/after records; Operators cannot read audit logs. No audit mutation endpoint exists. |
| API-09 | Overview counts name their scope explicitly and treat Shanghai day boundaries correctly; all roles with run-read permission may view them. |
| API-10 | OpenAPI describes request constraints, enums, decimal transport and response contracts; sanitized error and no-cache behavior are tested. |
| API-11 | MySQL integration exercises the HTTP layer against migrated data, including decimal readback, permissions and concurrent mutation conflicts. |
| API-12 | Full section diff review, tests, documented workflow/data flow and exact-head CI evidence precede the owner's Section 5 verification request. |

## Follow-ups and boundaries

R34-01 (legacy account identifiers) remains open before any affected legacy
upgrade and before Section 15 deployment. R34-02's offline timestamp correction
belongs to Section 4 closeout. No migration, new account role, export implementation,
machine intake or frontend implementation is planned in Section 5. Additional
business behavior requires an owner decision; technical API plumbing uses the
already approved stack and policy.

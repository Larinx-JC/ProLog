# Section 3: Authentication & Multi-Level Authorization

Status: implementation authorized by the owner's Section 2 verification on
2026-09-07; see [project status](../../PROJECT_STATUS.md).
Implementation, full review and CI verification are complete; evidence is
recorded in the [review report](../reviews/section-03-review.md).

Section 3 also closes the non-blocking R2-01/R2-02 review follow-ups: align
ORM/database defaults and their drift checks, and complete function comments.
The approved Section 2 migration's schema remains historical; authentication
schema changes use a new revision.

## Purpose and scope

Permitted people can obtain an account, sign in, and access only their allowed
operations. Accounts, sessions, and invitations remain on the local server.
The implementation uses the confirmed FastAPI/MySQL stack and the existing
Role, User, and AuditLog models.

This section delivers authentication and user-management services, migrations,
APIs, reusable authorization dependencies, and an API/CLI demonstration.
Production workflows remain in Section 4 and their APIs in Section 5.
Browser login, activation, and account-management screens arrive in Section 9.

## Confirmed policy

- Admin issues a single-use activation link and copies it for delivery through
  an existing trusted channel. The application does not need email delivery.
- Server-side sessions use HttpOnly cookies.
- Configurable session defaults: 30 minutes inactive and 12 hours absolute
  maximum. Background dashboard refreshes do not count as user activity.
- There is no public self-registration.
- Admin has full authority; Operator has production-entry authority without
  review; Reviewer reads production/log data and exports without entry or
  approve/reject authority. See [D04](../decisions.md).

## Resolved account decisions

The owner confirmed D16–D18 on 2026-09-07. Operators read all runs and may
edit their own active runs; activation is valid for 24 hours, recovery for
30 minutes; reissue revokes prior links; multiple sessions are permitted.
Local interactive Admin setup/recovery protects the final active Admin.

| Choice | Confirmed behavior | Decision reference |
| --- | --- | --- |
| Operator visibility and edit scope | View all runs; create runs and edit own active runs; no export or review. | D16 |
| Activation expiry | 24 hours; configurable; resending revokes the prior link. | D17 |
| Password recovery | Admin issues a single-use recovery link valid for 30 minutes; passwords are never disclosed. | D17 |
| Concurrent sessions | Permit multiple sessions, each subject to idle and absolute expiry. | D17 |
| First Admin and emergency recovery | Local CLI with an interactive password prompt; protect the final active Admin from disable/demotion. | D18 |

The [implementation brief](03-implementation.md) records password policy,
throttling, account normalization, activation URL handling, and CSRF design.

## Acceptance checklist

| ID | Scenario and expected result | Required verification |
| --- | --- | --- |
| AUTH-01 | Local first-Admin setup creates one account with a password hash and Admin role. Repeating or racing bootstrap cannot create another bootstrap Admin. No default credentials ship. | CLI success/failure tests; MySQL concurrent bootstrap test. |
| AUTH-02 | Only an active Admin can invite a user into an allowed role. Invalid/duplicate account data creates no partially provisioned user. Operator, Reviewer, and anonymous requests are denied. | Role matrix API tests; persisted rows and audit assertions. |
| AUTH-03 | A valid activation link sets the user's chosen password and enables the account. Invalid, expired, revoked, and already-used links fail without account changes. Two concurrent attempts have at most one success. | Before/at/after expiry unit tests; MySQL consumption race and rollback tests. |
| AUTH-04 | Login succeeds for an activated, enabled account with valid credentials. Wrong password, unknown account, disabled account, and unactivated account do not establish a session or reveal which condition applied. | API response, cookie, database, and audit assertions. |
| AUTH-05 | Successful login issues a fresh unpredictable session token. Reusing a caller-provided token cannot fix the user's session identifier. Only token digests are persisted; secrets are absent from logs and account responses. | Token rotation/rejection tests; storage and response inspection. |
| AUTH-06 | Server rejects sessions at the idle and absolute deadlines. Explicit foreground activity can extend idle expiry but cannot extend absolute expiry; background refresh cannot keep an idle session alive. | Injected-clock boundary tests and API activity classification tests. |
| AUTH-07 | Logout invalidates the server session and clears the cookie. Replaying it fails; repeated logout is harmless. Sessions and expiry remain meaningful across an application restart. | API replay tests and database-backed restart simulation. |
| AUTH-08 | Current-user responses contain only appropriate account fields. Every protected operation checks current account status and permissions server-side. Unknown roles have no implicit privileges. | Allowed/denied permission matrix and direct-API bypass attempts. |
| AUTH-09 | Account disable and role changes revoke affected sessions. A downgraded user cannot continue with old authority. Enforce the agreed final-Admin protection even under concurrent changes. | API tests, stale-session rejection, MySQL concurrent administration tests. |
| AUTH-10 | Password changes require proof of current authority. Recovery follows the approved procedure. Prior passwords and sessions become unusable after completion; tokens are single-use. | Change/recovery success and failure tests, session replay and race tests. |
| AUTH-11 | If temporary-password or forced-change accounts exist, they can only change their password or log out until the change completes. Activation with a user-chosen permanent password must set the flag consistently. | Restriction tests including direct access to protected routes. |
| AUTH-12 | Production uses Secure, HttpOnly, appropriately scoped SameSite session cookies over HTTPS. State-changing browser requests are protected against CSRF; GET cannot activate, reset, disable, or log out an account. | Cookie/config assertions; missing/wrong CSRF token and untrusted-origin rejection, including login. |
| AUTH-13 | Login and token-consumption attempts have documented throttling. The configured limits return a predictable response and expire/recover as specified. | Controlled-clock threshold/recovery tests; behavior across worker processes when supported. |
| AUTH-14 | Successful account changes and their audit records commit atomically. A failed write cannot leave a success audit or partial account change. Failure events carry no password/session/activation secret. | Injected persistence failures, rollback tests, audit inspection. |
| AUTH-15 | Production rejects placeholder secrets when required, invalid timeout settings, and unsafe authentication configuration. Database failure never silently grants access. | Environment-loading, startup, and API failure tests. |
| AUTH-16 | A new migration adds required invitation/session persistence without rewriting the approved Section 2 migration. Upgrade preserves existing users/roles; downgrade and drift/seed checks pass on disposable MySQL. | MySQL migration cycle with existing synthetic rows and integration assertions. |

Session expiration is enforced by the server. The chosen durations are
owner policy; tests must enforce both idle and absolute limits and rotate
credentials at authentication boundaries.
[OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

Activation/recovery tokens should be unpredictable, securely stored,
single-use, and expiring. Apply the recovery-token guidance to the confirmed
Admin-delivered link flow; it does not introduce an email requirement.
[OWASP recovery-token guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Use server validation for state-changing requests, including the selected
CSRF mechanism and origin checks. SameSite is an additional browser control.
[OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

## Implemented boundaries

| Component | Responsibility |
| --- | --- |
| AuthService | Authenticate credentials and coordinate login/password change. |
| SessionService | Issue, validate, expire, and revoke persistent sessions using an injectable clock. |
| InvitationService | Create and consume activation/recovery grants atomically. |
| UserService | Bootstrap/invite, disable, and change account privileges with audit records. |
| Permission policy / API dependencies | Map the agreed roles to operations and enforce current account state. |
| Shared repositories / transaction boundary | Keep each account mutation and audit write in one database transaction. |

The concrete classes and data flow are in [authentication](../authentication.md).
Use a server-side session store: a cookie containing a signed user/role payload
alone would not meet the agreed revocation requirement.

Persistence includes invitation/token digests, purpose, expiry,
issuer/recipient, consumption/revocation timestamps; and session token digests,
user association, creation/activity/expiry/revocation timestamps. Final column
names and relationships are documented with the Section 3 migration.

## Acceptance evidence map

All paths below are under `backend/tests/`. The review records executed counts
and the exact CI commit; this map states what the assertions establish.

| Criteria | Test evidence |
| --- | --- |
| AUTH-01, AUTH-02 | `test_auth_config_cli.py`, bootstrap/duplicate/permission tests in `test_auth_services.py`, non-Admin API rejection, MySQL bootstrap race. |
| AUTH-03 | Activation boundary/reissue/disable/single-use tests; failed-activation audit rollback; MySQL activation consumption race. |
| AUTH-04, AUTH-05 | Generic login rejection matrix, salted hash/rehash tests, API fixation/CSRF rotation, persisted digest and audit-secret assertions. |
| AUTH-06, AUTH-07 | Idle/absolute boundary tests, API background reads and foreground activity, API logout/replay and service restart tests. |
| AUTH-08, AUTH-09 | All capabilities and ownership cases, stale-session rejection, forced-change API checks, MySQL final-Admin race. Production transition eligibility remains Section 4. |
| AUTH-10, AUTH-11 | Password/recovery revocation and expiry tests, MySQL recovery race, forced-change service and actual-route rejection tests. |
| AUTH-12, AUTH-15 | Real environment-loading tests; cookie attributes; JSON/CSRF/origin/GET restrictions; safe validation and unavailable-database responses. |
| AUTH-13, AUTH-14 | Account/address/grant throttling, clock-controlled window recovery and restart; invitation/activation audit rollback tests on SQLite and invitation rollback on MySQL. |
| AUTH-16 | `test_auth_migrations.py` and MySQL existing-user upgrade/recovery/downgrade test; exact seeds; unchanged historical DDL; real changed-default detection. |

## Demonstration for handover

Use a disposable database with synthetic accounts:

1. Create the initial Admin locally and sign in through the API.
2. Issue and consume Operator and Reviewer activation links.
3. Show that repeating activation fails and that no raw credential is stored.
4. Demonstrate the role matrix using reusable protected test routes;
   production action endpoints are implemented in later sections.
5. Disable an account and show its old session is rejected.
6. Show deterministic idle/absolute expiry and password-change revocation.
7. Inspect audit records and run the migration checks.

Include executable commands, actual endpoint names, expected outputs, and
test references in the final Section 3 handover. Then repeat the relevant
walkthrough in the browser when Section 9 is implemented.

## Exit criteria

All AUTH criteria are met for the resolved policy; important functions have
tests and docstrings; applicable [testing improvements](../testing.md) pass;
the API/CLI demonstration and data-flow/class documentation are reviewable;
CI is green for the current PR head. Owner verification is still required
before merging Section 3 and advancing to Section 4.

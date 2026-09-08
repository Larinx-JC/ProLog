# Section 3 implementation brief

Authorized on 2026-09-07 after full Section 2 review. Section 2 merged as
`6b0509e`; work proceeds on `codex/section-03-authentication`.

## Confirmed account policy

- Operators can view all runs, create runs, and edit their own active runs;
  they cannot export or review. Admins retain full authority. Reviewers
  can view production data/logs and export, without entry/review authority.
- Activation grants last 24 hours; recovery grants last 30 minutes. These
  durations are configurable. Reissuing a grant revokes older grants.
- Multiple sessions are allowed, each with a 30-minute idle timeout and a
  12-hour absolute limit. Background refresh does not renew idle expiry.
- A local interactive CLI creates the first Admin and supports emergency
  recovery. No default credentials. The final active Admin is protected
  against disabling/demotion. These choices were confirmed by the owner.

## Engineering decisions

Use Argon2id password hashing (19 MiB, two iterations, one lane), independent
random tokens with 256 bits of entropy, and SHA-256 token digests in MySQL.
Passwords are 15–128 characters, with spaces/Unicode allowed and no forced
composition or periodic rotation. Do not normalize passwords. Account names
are trimmed lowercase ASCII identifiers (letters, numbers, dot, underscore,
hyphen), preserving the existing display-name field for Unicode names.
[Password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

Session cookies are HttpOnly, SameSite=Strict, and Secure in production.
Production requires HTTPS origins and a non-placeholder secret of at least
32 characters. Cookie names use the __Host- prefix when Secure is enabled.
JSON mutation endpoints require an allowed Origin and a CSRF token tied to
the HttpOnly session/pre-login cookie. GET requests never mutate accounts.
Login and activation return no-cache responses; validation errors omit input
values so passwords/tokens are not echoed. Activation/recovery links carry
tokens in a URL fragment for the later Section 9 UI, not a query string.

Authentication writes use a short database transaction protected by one seeded
authentication coordination row. This deliberately serializes authentication
changes for this small factory deployment, including grant consumption,
bootstrap, final-Admin checks, and session revocation. It avoids depending on
process-local locks and works across application workers. Production-domain
writes remain Section 4. The lock is a throughput tradeoff to measure before
larger deployment; password-input sizes and attempt rates are bounded.

Rate-limit counters persist in the database. Login is limited by normalized
account and client address; grant consumption is limited by client address.
Counter keys are hashed, failed attempts commit their counter/audit state,
and successful account writes commit atomically with their audit event.
Limits and windows are configurable; expired counters are pruned. Forwarded
headers are not trusted by application code; the deployment proxy must be
configured explicitly. Throttling may temporarily deny an account targeted
by repeated failures; it never disables the account permanently.

Auth timestamps use UTC-naive values with MySQL DATETIME(6) storage and an
injectable clock. Existing production DATETIME columns retain their approved
schema; timestamps are not used as concurrency tokens.

## Implementation sequence

1. Close the Section 2 metadata-default and function-comment follow-ups.
2. Add password/token helpers, configuration, and persistent auth models with
   a new migration. Keep the Section 2 migration's DDL unchanged.
3. Implement reusable session, invitation, account, and authorization services.
4. Add JSON APIs and the local Admin CLI.
5. Exercise acceptance success/rejection/boundary/race/rollback scenarios,
   including migrated MySQL and Windows/Linux unit CI.
6. Document API/CLI demonstrations, data flow, and class relationships;
   review the entire Section 3 diff and fix findings before requesting approval.

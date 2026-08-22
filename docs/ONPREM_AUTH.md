# On-premise access control (WO-31)

Authoritative product text: feature **On-Premise Access Control**. This note is the engineer mapping for **WO-35**.

## Deployment

| Environment | `AUTH_MODE` | Sign-in |
|-------------|----------------|---------|
| Local Compose | `disabled` (default) | Not required |
| On-premise Compose | `required` | Required for module routes |

`/health`, `/ready`, `/docs`, and `/openapi.json` stay reachable without a session.

## Roles

- **Operator** — all four modules; only their Owned Requests.
- **Administrator** — Operator plus add/disable/list operators. First administrator is created at deploy time, not through an unsigned-in UI.

## Session

- Identity + secret issued by an administrator.
- Session lasts while the operator is active and ends after eight hours idle, sign-out, or disable.
- Failed sign-in does not say whether the identity exists.

## Files

Uploads, generated reports, and MPP downloads are bound to the Operator who created the request handle. Another operator cannot status, retry, or download that handle.

## Audit

Append-only records for sign-in, sign-out, upload, generate, retry, download, and refused unsigned-in attempts. Retention matches request TTL (24 hours unless configured).

## Deferred

SSO, LDAP, TLS termination, and browsing another operator's files (except audit export).

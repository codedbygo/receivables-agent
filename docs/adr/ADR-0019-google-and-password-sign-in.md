# ADR-0019: Sign in as a person, with Google or with an email and password

- Status: Accepted
- Date: 2026-10-08
- Task: HACK-011
- Deciders: Savitha Sista (engineer; chose "both Google and email and password" on 2026-10-08)
- Area: auth
- Reversibility: awkward (users, password hashes and sessions become stored data)
- Supersedes in part: ADR-0013 (the per-role access codes for browser sign-in)

## Context

ADR-0013 signs a browser in with one shared access code per role. Every action is recorded against the seeded user
for that role ("Asha (Admin)"), so the audit trail cannot say who approved a message or started a real call. A
leaked or departed person's code can only be revoked by changing it for everyone. The console now places real
Twilio calls and sends real email (ADR-0017, ADR-0018), and ADR-0013 itself said to revisit this for multi-user use.

Facts that shaped the options: a Google Cloud OAuth client and the HMAC-signed state already exist (ADR-0018); the
API runs on Vercel serverless functions, so a session cannot live in server memory; the `users` table and the
admin, collector and viewer roles (ADR-0009) stay.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Google sign-in only (recommended) | people without a Google account cannot sign in | a team that all has Google accounts |
| Email and password only | we own hashing, reset, lockout and 2FA; no Google 2FA for those who have it | users with no Google account |
| Google and email and password (chosen) | both paths to build, test and secure | a mixed team, some with Google, some without |
| Hosted provider (Clerk, Auth0) | a new vendor, SDK and monthly cost; user data outside our database | SSO for several client companies |
| Keep the access codes | no per-person identity | a single shared demo |

## Decision

- A person is a row in `users` with an email, a role and an active flag. Only an admin adds, changes or removes one;
  nobody signs themselves up.
- **Google:** the OpenID Connect code flow on the existing OAuth client, scopes `openid email` only. Sign-in
  succeeds only when Google reports the email verified and it matches an active user. These scopes need no Google
  verification review.
- **Email and password:** hashed with `hashlib.scrypt` from the standard library (per-user salt, constant-time
  compare), so no new dependency. Five wrong passwords in a row lock the account for 15 minutes, and a wrong
  password and an unknown email get the same answer in the same time. An admin sets a new password (which also
  clears a lock); a forgot-password email link is a later step.
- **Session:** a random value in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie on `/api`, valid 12 hours; the
  existing `sessions` table stores only its SHA-256. A database row (not a signed cookie) works across serverless
  instances and can be revoked: signing out or switching a person off ends it at the next request.
- `ADMIN_TOKEN` stays for scripts (it wins over a cookie the same client carries), and `DEMO_OPEN_ROLES` stays for a
  laptop and the tests; the per-role browser codes (`COLLECTOR_TOKEN`, `VIEWER_TOKEN`, and the code screen) go.
- The seeded demo accounts have a published password, so they are refused unless `DEMO_OPEN_ROLES` is on.
  `BOOTSTRAP_ADMIN_EMAIL` names the first admin of a hosted deployment, created the first time that email signs in
  with Google or with `BOOTSTRAP_ADMIN_PASSWORD`; never re-created or switched back on afterwards, so an admin who
  turns that person off stays in charge.
- Audit rows record the signed-in user, not the role's seeded user.

## Consequences

- Real names in the audit trail; one person can be removed without touching anyone else.
- We own the password path: hashing parameters, lockout, reset tokens and their tests. It gets a `/cso --diff` (or
  claude-security) scan before the change request, as the security rules require for auth.
- Google in Testing mode admits only listed test users (up to 100); publishing the app removes that limit and, for
  `openid email` alone, needs no review.
- Hosted deployments set `BOOTSTRAP_ADMIN_EMAIL` for the first admin, since nobody can sign up; clear it once real
  admins exist.
- Not built yet: a forgot-password email link (an admin sets a new password instead), changing your own password,
  and 2FA for password users.

## Commits us to

A People panel on the Admin page, migration 0010 (`active`, `failed_logins`, `locked_until` on `users`), the
cookie session on every route, and retiring the browser access codes from the console and the hosted environment.

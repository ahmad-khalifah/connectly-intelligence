# Milestone 3: Accounts, roles, audit log, community claims and the Connectly brand

Completed 10 November 2026.

## What was built

**Accounts and roles (backend).**

- Four roles. Admin can do everything. Researcher adds and reviews community claims. Company will manage its own solutions in Milestone 4. Viewer has read-only access.
- Every endpoint needs a signed-in user, except `/health` and sign-in.
- Password and session security:
  - passwords are hashed with Argon2id, at least 12 characters;
  - sessions are HS256 tokens signed with `CONNECTLY_SECRET_KEY`, and production refuses to start without a key of at least 32 characters;
  - every account has a token version, so a password change, a role change, deactivation or "sign out everywhere" revokes all of that account's earlier sessions.
- Sign-in protection:
  - an account locks for 15 minutes after 5 wrong passwords;
  - each client address is limited to 30 attempts in 10 minutes;
  - unknown e-mails and wrong passwords get the same response and take the same time.
- Administrators create accounts. Each new account gets a temporary password that is shown once and must be changed before anything else can be done.
- The last active admin cannot be demoted or disabled.
- The command line has `connectly users create` and `connectly users list`.

**Audit log.**

- Every sign-in, failed sign-in, account change and claim change is recorded with who did it, when, from which address, and before-and-after values.
- Passwords are never logged.
- Admins can read the log in the app.

**Community claims.**

- Researchers can record qualitative facts about a ward, LGA, state or settlement, such as market days, economic activities or connectivity observations. Each claim needs a source.
- Claim rules:
  - a claim cannot be modelled or AI-generated;
  - it must be reviewed by someone other than its author;
  - any edit sends it back for review;
  - retiring a claim keeps it on record.
- Each claim's full history is available.
- Free text containing a phone number or e-mail address is refused, because Connectly stores facts about places, not about residents.

**Web app.**

- Sign-in page, change-password page, account page (including "sign out everywhere"), user administration and audit log.
- The browser never holds the session token:
  - it lives in an httpOnly, SameSite=Lax cookie that is HTTPS-only in production;
  - the app's own server forwards API calls, but only to `/api/v1/` paths, and never to the routes that issue tokens;
  - state-changing requests from another origin are refused.

**Brand.**

- The official logo is used in the navigation and on the sign-in page. Its symbol is used as the browser icon and on loading screens.
- The colours come from the logo: maroon `#6B1420` and gold `#D9A441`.
- Fonts are Poppins for headings and Inter for text. Both are open-licensed and served by the app itself.
- See `docs/brand/README.md`.

## Tests

- **Backend:** 103 tests pass (30 new). They cover:
  - sign-in, lockout and the per-address limit;
  - tampered, expired, wrong-key and `alg=none` tokens;
  - revocation on logout, password change, role change and deactivation;
  - the temporary-password flow and password rules;
  - admin-only endpoints and protection of the last admin;
  - that the audit log never contains passwords;
  - the full claim lifecycle, including the rule that authors cannot review their own claims;
  - validation, and the personal-data guard.
- **Frontend:** lint, type check and production build pass.
- **End to end:** a browser walkthrough was run against the production build. It checked:
  - redirect to sign-in;
  - a wrong password;
  - the forced password change;
  - the overview, explorer and user administration pages;
  - the audit log;
  - that the session cookie is httpOnly and not readable by page scripts;
  - that the forwarder refuses the token routes, non-API paths and cross-origin posts;
  - sign-out;
  - the mobile layout.

## Limitations

- The per-address sign-in limit is kept in memory, per API process. Account lockout is stored in the database and applies everywhere.
- There is no self-service registration or e-mail password reset. No e-mail service is used, because the free tiers are not dependable. Admins reset passwords and pass them on privately.

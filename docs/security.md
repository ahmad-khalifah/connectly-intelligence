# Security review

Review date: 10 November 2026. Scope: the API, the web app, the Docker setup and their
dependencies.

## Controls in place

| Area | Control | Where |
| --- | --- | --- |
| Authentication | Argon2id password hashes; HS256 tokens signed with `CONNECTLY_SECRET_KEY` (≥ 32 characters; production refuses to start without it); 8-hour sessions | `core/security.py` |
| Session revocation | Per-account token version; incremented on password change, role or organisation change, deactivation, admin password reset and "sign out everywhere" | `models/auth.py`, `api/deps.py` |
| Sign-in abuse | Account locks for 15 minutes after 5 failures. Per-address limit of 30 attempts per 10 minutes. Identical response for unknown e-mail and wrong password, with a dummy hash so timing matches. | `api/routers/auth.py` |
| New accounts | Created by admins only; temporary password shown once and must be changed before anything else works | `api/routers/auth.py` |
| Authorisation | Every endpoint except `/health` and sign-in needs a session. Role checks for admin, researcher and company actions. Ownership checks for company records and reports. The last active admin cannot be removed. Authors cannot review their own claims. | `api/deps.py`, routers |
| Browser session | Token kept in an httpOnly, SameSite=Lax cookie, Secure in production. The browser never sees it. | `frontend/src/app/api/auth/*` |
| CSRF | SameSite cookie, plus an Origin check on every state-changing request through the web app | `frontend/src/lib/server.ts` |
| Backend proxy | Forwards only `/api/v1/…`, never the routes that return tokens; rejects path traversal | `frontend/src/app/api/backend/[...path]/route.ts` |
| Open redirects | The post-sign-in destination must be a same-site path | `safeNext` (unit-tested) |
| SQL injection | All values are bound parameters. The few interpolated identifiers come from code constants or validated enums (reviewed with a search of every f-string SQL statement). | services, routers |
| XSS | React escapes output and there is no `dangerouslySetInnerHTML`. PDF text is XML-escaped. | |
| Headers | API: `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `no-store`. Web: CSP (`frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`), `nosniff`, `DENY`, referrer and permissions policies. The `X-Powered-By` header is removed. | `api/main.py`, `next.config.ts` |
| API exposure | The API docs are off in production. In Docker the API port is not published; only the web container can reach it. | `docker-compose.yml` |
| Personal data | No resident data is modelled. Free text containing a phone number or e-mail address is refused. The audit log never stores passwords. | `services/personal_data.py` |
| Audit | Append-only log of sign-ins, failed sign-ins and every change, with before and after values and the client address | `services/audit.py` |
| Containers | Non-root users, minimal base images, health checks | `backend/Dockerfile`, `frontend/Dockerfile` |
| Dependencies | `pip-audit` and `npm audit --omit=dev` run in CI. Both are clean at review time. | `.github/workflows/ci.yml` |

## Known limitations (not critical)

- **CSP allows inline scripts** (`'unsafe-inline'`), which Next.js streaming needs without a
  nonce setup. XSS risk is low because React escapes all output.
- **The per-address sign-in limit lives in memory**, so each API process counts separately.
  Account lockout is stored in the database. Behind a reverse proxy, set
  `TRUSTED_PROXY_HOPS` so the real client address is used.
- **No multi-factor authentication or e-mail password reset.** No free, dependable e-mail
  service is assumed; admins reset passwords.
- **Development dependencies** (the ESLint toolchain) have 8 moderate advisories in
  `minimatch`. They are not part of the running application.
- **The PostGIS port is published to the host** in `docker-compose.yml` for local use. Remove
  the `ports` entry on a shared server.
- **HTTPS must be provided by a reverse proxy** (for example Caddy or nginx) when deploying;
  see `docs/deployment.md`.

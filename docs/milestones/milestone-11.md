# Milestone 11: Security, tests and Docker verification

Completed 10 November 2026.

## Security

The review is in `docs/security.md`. Changes in this milestone:

- **Web app headers:** content security policy, frame denial, MIME sniffing protection, referrer and permissions policies. The `X-Powered-By` header is removed.
- **Client address:** taken from the right-hand end of `X-Forwarded-For`, using the `TRUSTED_PROXY_HOPS` setting, so a client cannot spoof its address to evade sign-in limits.
- **Unique control ids:** form controls shared between pages now have unique ids. Next.js keeps visited pages mounted but hidden, so a label could point at a hidden control on another page.
- **SQL review:** every SQL statement that interpolates text was reviewed. Only code constants and validated enums are interpolated.
- **Dependency audits:** `pip-audit` and `npm audit --omit=dev` are clean.

## Tests

| Suite | Count | Where it runs |
| --- | --- | --- |
| Backend unit, API and real-data tests | 152 | Locally and in CI against PostGIS |
| Frontend unit tests (Node test runner) | 3 | Locally and in CI |
| Browser tests (Playwright) | 8 (7 desktop, 1 mobile) | Locally against the development stack, and in CI against the Docker stack |
| Lint, type checks, production build, dependency audits | — | Locally and in CI |

The browser tests cover:

- the sign-in redirect and security headers;
- a wrong password, then the forced password change, with the httpOnly cookie checked;
- real counts on the dashboard (774 LGAs, 9,308 wards);
- the Adamawa choropleth, and the Bille profile (12,867 people);
- the directory flow: create an organisation and a solution, publish, match, save a report, download the PDF, retire;
- the gap reporting on the Needs, Intelligence and Market entry pages;
- the administration pages and sign-out;
- the dashboard on mobile.

## Docker, independently verified

The `stack` job in GitHub Actions, run 42867637285 on commit `7ca29b1`, passed every step:

1. It built `backend/Dockerfile` (Python 3.12 slim, non-root, migrations on start) and `frontend/Dockerfile` (Next.js standalone, non-root).
2. It started PostGIS, the API and the web app with `docker compose --profile app up --wait`. All three containers reported healthy.
3. It confirmed that the API port is not reachable from the host.
4. It ran `connectly bootstrap` inside the API container. This loaded 1 country, 37 states, 774 LGAs and 9,308 wards from the real downloads, and the state-code check passed for all wards.
5. It created an admin account with the CLI.
6. It ran all 8 browser tests against `http://localhost:3000`: **8 passed**.

Docker could not run in the build workspace, because no daemon is available there. CI is therefore the independent verification.

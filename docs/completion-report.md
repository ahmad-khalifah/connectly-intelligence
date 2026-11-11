# Connectly Intelligence: completion report

10 November 2026, re-verified 11 November 2026 · repository `ahmad-khalifah/connectly-intelligence`, branch `main`

The 11 November clean-machine re-verification and the two map fixes it led to are recorded in
[milestones/verification-2026-11-11.md](milestones/verification-2026-11-11.md). The nationwide
coverage changes made the same day are recorded in
[milestones/nationwide-coverage.md](milestones/nationwide-coverage.md).

## 1. Summary

All twelve steps of the agreed workflow are implemented, tested and pushed. The platform runs
end to end from a clean environment using Docker. GitHub Actions built the images, started the
stack, loaded the real boundary data and passed all browser tests against it.

Everything is free and open source, with no paid API, map service, dataset or hosting.

The platform contains **no invented data**:

- The **national geography** (country, 37 states, 774 LGAs, 9,308 wards) and **modelled ward
  population** load automatically from openly licensed GRID3 files, with checksums.
- **Facilities, settlements and survey statistics** are fully supported, but they must be
  downloaded on your machine. The build environment could reach only GitHub.
- The **technology directory** starts empty, because no open register exists. Records are
  entered by admins or submitted by companies for review.

Until those datasets are loaded, the needs, matching and market entry pages say "not enough
data" rather than producing numbers. That is the intended behaviour.

## 2. What is implemented

| Brief section | Implementation |
| --- | --- |
| Sectors (all 8; 3 priority) | Stored as data (new sectors are rows, not code), with need categories, indicator definitions and recorded data gaps |
| A. Community Intelligence Database (18 fields) | Boundaries for country, state, LGA and ward; settlements and facilities (point-in-polygon linked); observations with source, period, interval, value type and verification; community claims with a review workflow; profile pages covering every field, with missing data listed |
| B. Technology Solutions Database (20 fields) | Organisations and solutions with structured requirements (internet, device, power, literacy, languages, channels, accessibility, partnerships), coverage by state, LGA or ward (operating or expansion interest), pricing, sources and verification; admin entry, company self-submission with review, YAML import |
| 4. Community intelligence engine | Intelligence briefs for any area and sector. They have ten sections built from retrieved evidence, every statement is cited and tagged fact, derived, recommendation or gap, and confidence and limitations are stated. |
| 5. Matching engine (8 criteria) | Relevance, suitability, availability, affordability, internet and device, language, distribution and feasibility, each with reason and evidence. Unknown criteria lower confidence instead of passing or failing. No matching on sector alone. |
| 6. Market entry (12 outputs) | Candidate areas ranked by gap, fit, reach and competition (no score without evidence of need). The twelve outputs are tagged. Demand, partnerships and costs are never estimated. |
| 7. Mapping | MapLibre explorer from country to ward; choropleths by any indicator with values at that level; sector filter; facility and settlement layers; works offline without a tile service |
| 8. Data sources | Manifest per dataset (source, version, licence and its evidence, limitations, checksum); ingestion audit; Data sources page; `docs/data-ingestion.md` |
| 9. AI architecture | Separate components for data management, geographic analysis, processing, segmentation (needs assessment), matching, scoring, evidence retrieval and reasoning. An optional self-hosted model (Ollama or any OpenAI-compatible server) only summarises cited evidence; replies with an uncited sentence, an unknown evidence id or an invented number are rejected. |
| Interface | Dashboard of live counts, explorer, profiles, intelligence, needs, matching, market entry, directory, reports with branded PDF export, administration (users, audit, review queue, dataset loads) |
| Security | Four roles; Argon2id; revocable sessions; lockout and rate limits; httpOnly cookie through a same-origin proxy; CSRF origin checks; security headers; audit log; personal-data guard. See `docs/security.md`. |
| Brand | The official logo, converted from the supplied PDF without changes, is used in the navigation, sign-in page, loading screens, browser icon, footer and PDF reports. Maroon and gold come from the logo; Poppins and Inter are self-hosted. See `docs/brand/README.md`. |

Migrations: `0001` to `0005`, applied and checked for drift. Milestone reports:
`docs/milestones/`.

## 3. What is tested

| Check | Result |
| --- | --- |
| Backend tests (`pytest`), including six checks against the real loaded data | 163 passed (152 at first delivery; 11 added on 11 November) |
| Frontend unit tests | 3 passed |
| Browser tests (Playwright): sign-in and forced password change, dashboard, explorer, profile, directory to matching to PDF, needs, intelligence, market entry, admin, sign-out, mobile | 8 passed locally and 8 passed in CI against Docker |
| Lint and format (ruff, ESLint), type check, production build | Pass |
| Dependency audits (`pip-audit`, `npm audit --omit=dev`) | No known vulnerabilities |
| Docker stack (CI job `stack`, run 42867637285) | Images built, three containers healthy, API not exposed, bootstrap loaded 1 + 37 + 774 + 9,308 boundaries, browser tests passed |

Each milestone was also walked through in a browser against the production build, with
screenshots reviewed. Temporary records created for those checks were deleted afterwards.

## 4. Final delivery requirements

| # | Requirement | Status |
| --- | --- | --- |
| 1 | All modules implemented | Done (section 2) |
| 2 | Migrations complete | Done: `0001`–`0005`; `alembic check` clean |
| 3 | Ingestion documented | Done: `docs/data-ingestion.md` |
| 4 | All available datasets integrated and validated | Every dataset reachable from the build environment is loaded and validated. The rest have tested loaders, manifests and exact instructions (section 6). |
| 5 | All tests pass | Done (section 3) |
| 6 | Docker works or is independently verified | Independently verified in GitHub Actions (section 3) |
| 7 | Environment variables documented | Done: README "Configuration"; `.env.example` files |
| 8 | README install instructions complete | Done: Docker quick start and development set-up |
| 9 | No known critical security issues | None known; non-critical limitations listed in `docs/security.md` |
| 10 | Starts from a clean environment using the docs | Verified by the CI `stack` job, which follows the README steps |

## 5. What depends on your local verification

1. **Clone and run** the Docker quick start, then the checklist in `docs/deployment.md`,
   section 1.
2. **Download and load the external datasets** as national files, in this priority order (see
   [data-ingestion.md](data-ingestion.md); `--within-state` is only for trying a file on one state):
   - GRID3 health facilities v3.0 (24 states) and v2.0 (all other states);
   - OpenStreetMap (one command);
   - OpenCelliD (needs a free token);
   - GRID3 settlements;
   - the NDHS 2023-24 API;
   - EFInA and NCC tables, entered from the reports.

   Each loader has been tested with synthetic files of the same format, but not with the real
   files. If a real file's column names differ, the loader stops and lists the actual columns.
   Add the right name in the manifest and run it again.
3. **Confirm the GRID3 licences.** Several GRID3 manifests are marked "licence not verified",
   because the GRID3 pages could not be opened from here. Read each page, then set
   `licence_verified` and `commercial_use_allowed`.
4. **Confirm the ward population source.** The values match WorldPop/NPC v2.0. Confirm the
   attribution on the GRID3 or WorldPop page, then mark the dataset verified.
5. **AI summaries with Ollama.** The checking logic is tested with a stand-in model, but no
   live model was run here (`docs/ai.md`).
6. **Directory content.** Add real organisations and solutions from their own sources, or
   invite companies to submit them. Matching and market entry become useful as records are
   added.
7. **HTTPS deployment**, with a reverse proxy and secure cookies (`docs/deployment.md`).

## 6. Data limitations

- **Loaded:** boundaries (GRID3, CC BY 4.0), the April 2022 wards (GRID3 Operational Wards
  v4.0 is newer and can replace them after a manual download), modelled ward population with
  95% intervals (about 2019, unverified attribution), and the GRID3 urban flag.
- **Needs local download:** GRID3 health facilities (v3.0 covers 24 states; Taraba and Plateau
  need v2.0), GRID3 settlement names and extents, GRID3 education facilities (December 2020),
  OpenCelliD cell sites (crowdsourced; locations, not coverage), OpenStreetMap, NDHS 2023-24
  state indicators, EFInA A2F 2023 and NCC subscriptions (both state level, entered by hand
  with page references).
- **No open source exists for:**
  - a census since 2006;
  - agent banking and mobile money agent locations;
  - operator coverage maps (speed tests are non-commercial only);
  - crop production by LGA;
  - current settlement electrification;
  - economic activities per community;
  - a register of technology solutions;
  - market demand, prices and incomes at community level.

  These appear as recorded data gaps in the app. Where they matter, the analyses say
  "unknown" instead of estimating.
- **State-level survey values** (DHS, EFInA, NCC) are shown on LGA and ward profiles only as
  labelled context. They never colour or rank smaller areas.
- **Agriculture and transport** have no open indicator yet, so they cannot be scored. The app
  says so.
- **Distances** are straight-line, not travel time.

## 7. Notes and decisions to review

- **Favicon and loading mark.** These use the symbol from the official logo, cropped and
  otherwise unchanged. If you would prefer a different icon, replace
  `frontend/public/brand/connectly-mark.svg` and `frontend/src/app/icon.svg`.
- **No dark theme.** The logo is defined for light backgrounds and was not to be recoloured.
- **Hosting.** The brief suggested Vercel and managed PostgreSQL, but their free tiers are
  limited and change over time. The Docker setup runs on any host; `docs/deployment.md` covers
  a single server with free HTTPS (Caddy).
- **Scoring weights** (needs, matching and market entry) are documented in
  `docs/methodology.md` and kept in one file each. They are a starting point to review with
  domain experts.

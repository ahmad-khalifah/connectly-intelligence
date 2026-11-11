# Connectly Intelligence

Community intelligence and technology-matching platform for Nigeria, by Connectly
Technologies. It helps technology providers, development organisations and researchers find
underserved communities, understand their needs from evidence, and match them with suitable
solutions. It covers all 36 states and the FCT, every LGA and ward, and settlements wherever
reliable data exists. Adamawa was the first state used to validate the pipelines; nothing in
the application is limited to it. Where a dataset covers only some states, the dashboard's
coverage table shows which, and other states get "no data", never zero.

**Ground rule:** every value carries its source, period, licence, value type (measured,
modelled, derived, estimated, assumed, AI-generated) and verification status. Missing data is
recorded as a gap and shown to users. Nothing is invented to fill a page.

| | |
| --- | --- |
| Modules | Community intelligence database · explorer with indicator maps · community profiles · community claims with review · technology solutions directory with company self-submission · needs assessment · technology matching (8 criteria) · market entry intelligence · intelligence briefs with optional self-hosted AI · saved reports with PDF export · accounts, roles and audit log |
| Sectors | Healthcare, telecommunications and connectivity, financial services (priority); education, agriculture, clean energy, commerce and SMEs, transport and logistics |
| Data loaded automatically | Nigeria, 37 states, 774 LGAs, 9,308 wards (GRID3, CC BY 4.0); modelled ward population with 95% intervals; urban classification |
| Data loaded from local downloads | Health and education facilities, settlements, mobile network sites, OpenStreetMap, NDHS 2023-24, EFInA, NCC. See [docs/data-ingestion.md](docs/data-ingestion.md). |
| Cost | $0. Free, open-source software and openly licensed data only. No paid APIs, map services or hosting. |

## Contents

1. [Quick start with Docker](#quick-start-with-docker)
2. [Development setup](#development-setup)
3. [Loading more data](#loading-more-data)
4. [Configuration](#configuration)
5. [Commands](#commands)
6. [Tests](#tests)
7. [Repository layout](#repository-layout)
8. [Documentation](#documentation)

## Quick start with Docker

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (free for
personal use, education and small businesses) or Docker Engine with Compose v2.

```bash
git clone https://github.com/ahmad-khalifah/connectly-intelligence.git
cd connectly-intelligence
cp .env.example .env
```

Edit `.env`:

- set `CONNECTLY_SECRET_KEY` to the output of
  `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`;
- set `POSTGRES_PASSWORD`;
- keep `COOKIE_SECURE=false` while you use `http://localhost`.

Then:

```bash
docker compose --profile app up -d --build --wait
docker compose exec api connectly bootstrap
docker compose exec api connectly users create --email you@example.org --name "Your Name" --role admin
```

- `bootstrap` applies migrations, loads reference data, then downloads about 40 MB of boundary
  files from GitHub-hosted mirrors, verifies their checksums and loads them. It takes a few
  minutes.
- `users create` prints a **temporary password**.

Open <http://localhost:3000>, sign in with the temporary password, and choose your own.

Stop with `docker compose --profile app down`. Your data stays in Docker volumes; `down -v`
deletes it.

## Development setup

You need **Python 3.11+**, **Node.js 22**, and Docker (for the database) or a local
PostgreSQL 16 with PostGIS 3.

### 1. Database

```bash
docker compose up -d db       # PostgreSQL + PostGIS on localhost:5432
```

This creates `connectly` (your data) and `connectly_test` (wiped by the tests).

<details>
<summary>Without Docker</summary>

Install PostgreSQL 16 and PostGIS 3, then as a superuser:

```sql
CREATE ROLE connectly LOGIN PASSWORD 'connectly' CREATEDB;
CREATE DATABASE connectly OWNER connectly;
CREATE DATABASE connectly_test OWNER connectly;
\c connectly
CREATE EXTENSION postgis;
\c connectly_test
CREATE EXTENSION postgis;
```
</details>

### 2. API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                 # set CONNECTLY_SECRET_KEY (any 32+ characters)
connectly bootstrap
connectly users create --email you@example.org --name "Your Name" --role admin
uvicorn connectly.api.main:app --reload --port 8000
```

API documentation (development only): <http://localhost:8000/docs>

### 3. Web app

```bash
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

The web app calls the API at `http://localhost:8000` by default (set `API_URL` in
`frontend/.env.local` to change it).

## Loading more data

The build environment could reach only GitHub, so facility, settlement and survey files have
to be downloaded on your machine. [docs/data-ingestion.md](docs/data-ingestion.md) gives, for
each dataset, the exact file, its official source, its licence status and the command to load
it. For example, for the OpenStreetMap extract for Nigeria (ODbL):

```bash
connectly ingest fetch osm-nga-geofabrik
connectly ingest load osm-nga-geofabrik
connectly derive
```

With Docker, prefix the commands with `docker compose exec api`. To copy a manual download into
the container, use
`docker compose cp ./file.geojson api:/data/manual/file.geojson`.

## Configuration

### API (`backend/.env`, or the `api` service in `docker-compose.yml`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONNECTLY_DATABASE_URL` | `postgresql+psycopg://connectly:connectly@localhost:5432/connectly` | Database |
| `CONNECTLY_TEST_DATABASE_URL` | `…/connectly_test` | Database the tests wipe |
| `CONNECTLY_SECRET_KEY` | none | Signs sessions; 32+ characters; **required in production** |
| `CONNECTLY_ENVIRONMENT` | `development` | `production` disables `/docs` and requires the secret key |
| `CONNECTLY_ACCESS_TOKEN_MINUTES` | `480` | Session length |
| `CONNECTLY_LOGIN_MAX_FAILURES` / `CONNECTLY_LOGIN_LOCK_MINUTES` | `5` / `15` | Account lockout |
| `CONNECTLY_LOGIN_IP_LIMIT` / `CONNECTLY_LOGIN_IP_WINDOW_SECONDS` | `30` / `600` | Sign-in attempts per client address |
| `CONNECTLY_TRUST_PROXY_HEADERS` | `false` | Read the client address from `X-Forwarded-For` (only when the API is reachable solely through the web app or a proxy) |
| `CONNECTLY_CORS_ORIGINS` | `http://localhost:3000` | Browser origins allowed to call the API directly |
| `CONNECTLY_DATA_DIR` | `<repo>/data` | Downloaded and manual dataset files |
| `CONNECTLY_DOWNLOAD_TIMEOUT` | `300` | Download timeout, in seconds |
| `CONNECTLY_AI_PROVIDER` | `none` | `none`, `ollama` or `openai_compatible` (self-hosted only; see [docs/ai.md](docs/ai.md)) |
| `CONNECTLY_AI_BASE_URL` / `CONNECTLY_AI_MODEL` / `CONNECTLY_AI_API_KEY` | `http://localhost:11434` / `llama3.1:8b` / none | Model server |

### Web app (`frontend/.env.local`, or the `web` service)

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_URL` | `http://localhost:8000` | Where the web server reaches the API |
| `COOKIE_SECURE` | `true` in production builds | Set `false` only for plain-http testing |
| `TRUSTED_PROXY_HOPS` | `0` | Reverse proxies in front of the web app |
| `NEXT_PUBLIC_BASEMAP_STYLE_URL` | none | Optional free MapLibre basemap style. Without it, maps work offline on a plain background. |

### Docker Compose (`.env` in the repository root)

The variables are `CONNECTLY_SECRET_KEY`, `POSTGRES_PASSWORD`, `COOKIE_SECURE`,
`TRUSTED_PROXY_HOPS`, `CONNECTLY_AI_PROVIDER`, `WEB_PORT` (default 3000) and `DB_PORT`
(default 5432).

## Commands

| Command | What it does |
| --- | --- |
| `connectly bootstrap` | Migrate, seed, download and load the boundaries and wards, compute derived values |
| `connectly db upgrade` / `connectly db check` | Apply migrations / check the database and PostGIS |
| `connectly seed` | Sectors, needs, indicator definitions, recorded data gaps |
| `connectly ingest list` | Every known dataset, its status and whether a local copy exists |
| `connectly ingest fetch <key>` | Download a dataset with a direct link or API |
| `connectly ingest load <key> [--file PATH] [--within-state NAME]` | Validate and load a dataset |
| `connectly ingest runs` | History of dataset loads |
| `connectly derive-rollups` / `connectly derive` | Population roll-ups / derived indicators |
| `connectly users create --email E --name N --role R` | Create an account (admin, researcher, company, viewer) |
| `connectly users list` | List accounts |
| `connectly directory import FILE.yaml` | Add or update directory records ([format](docs/directory.md)) |

## Tests

```bash
cd backend && pytest -q && ruff check .        # 163 tests, against connectly_test
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Browser tests (`frontend/e2e`) run against a running stack; see
[frontend/e2e/README.md](frontend/e2e/README.md). GitHub Actions runs all of the above on
every push. It also builds the Docker images, starts the full stack, loads the real
boundaries and runs the browser tests against it.

## Repository layout

```
backend/
  connectly/
    api/          FastAPI app; routers for geography, community, claims, directory, needs,
                  matching, market entry, intelligence, reports, auth, audit
    ai/           evidence retrieval, briefs, optional model providers and answer checks
    core/         settings, database, security
    ingest/       dataset pipelines; manifests/ has one YAML per dataset (source, licence, fields)
    models/       SQLAlchemy models
    reports/      PDF rendering (with the official logo)
    services/     profiles, needs assessment, matching, market entry, directory, audit
    taxonomy/     sectors, needs, indicators, data gaps, need models
  alembic/        migrations 0001–0005
  tests/          unit, API and real-data tests
frontend/
  src/app/        pages (sign-in, overview, explorer, profiles, intelligence, needs,
                  matching, market entry, directory, reports, admin) and the API proxy
  src/components/ UI components; public/brand/ holds the official logo files (do not edit)
  e2e/, tests/    browser tests and unit tests
docker/           database init script
docs/             methods, data ingestion, directory, AI, security, deployment, milestones,
                  brand/ (the original logo PDF)
```

## Documentation

- [Data ingestion](docs/data-ingestion.md): every dataset, its source, licence and load command
- [Methods](docs/methodology.md): value types, gap scores, matching, market entry
- [Directory](docs/directory.md): fields, review workflow, import format
- [AI layer](docs/ai.md): retrieval, the checks on model output, Ollama set-up
- [Security review](docs/security.md)
- [Deployment](docs/deployment.md)
- [Brand assets](docs/brand/README.md)
- [Milestone reports](docs/milestones/) and the [completion report](docs/completion-report.md)

## Data and licences

Boundaries © GRID3, licensed CC BY 4.0, distributed by
[geoBoundaries](https://www.geoboundaries.org). The Data sources page in the app lists every
dataset, its licence and the evidence for it, its checksum, and every known data gap.

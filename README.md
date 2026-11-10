# Connectly Intelligence

Community intelligence and technology-matching platform for Nigeria. It helps technology
providers and development organisations find underserved communities, understand their
needs and match them with suitable solutions.

**Ground rule:** every value carries its source, date, licence and verification status.
Missing data is recorded as a gap and shown to users. Nothing is invented to fill a page.

| | |
| --- | --- |
| Status | Milestones 1–8 complete: boundaries; wards, population and community database; accounts, roles, audit log and brand; technology solutions directory; explorer with indicator maps and community profiles; needs assessment, technology matching and market entry ([methods](docs/methodology.md)). Reports in [docs/milestones/](docs/milestones/). |
| Coverage | Nigeria: country, 37 states, 774 LGAs, 9,308 wards (GRID3, CC BY 4.0) with modelled ward population. Facilities, settlements and survey statistics load from local downloads: see [docs/data-ingestion.md](docs/data-ingestion.md). |
| Cost | $0. Everything runs locally on free, open-source software and openly licensed data. No paid APIs. |

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, GeoPandas
- **Database:** PostgreSQL 16 + PostGIS 3.4
- **Frontend:** Next.js 16, TypeScript, Tailwind CSS 4, MapLibre GL
- **AI:** not integrated yet. Planned through a swappable interface that can use local open models (for example via Ollama).

## Run it on your computer

You need **Git**, **Python 3.11+**, **Node.js 20+**, and either **Docker Desktop** (easiest) or a local PostgreSQL 16 with PostGIS.

### 1. Database

```bash
docker compose up -d          # PostgreSQL + PostGIS on localhost:5432
```

This creates two databases: `connectly` (your data) and `connectly_test` (wiped by the tests).

<details>
<summary>Without Docker</summary>

Install PostgreSQL 16 and PostGIS 3, then run as a superuser:

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

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cp .env.example .env                 # then set CONNECTLY_SECRET_KEY (see below)
connectly bootstrap                  # migrate, seed, download + load boundaries and wards
connectly users create --email you@example.org --name "Your Name" --role admin
uvicorn connectly.api.main:app --reload --port 8000
```

`connectly bootstrap` downloads about 40 MB of boundary files from GitHub-hosted mirrors of
geoBoundaries into `data/raw/`, verifies their checksums, and loads them.
`connectly users create` prints a temporary password; sign in with it and choose your own.
API docs (development only): http://localhost:8000/docs

Generate the secret key with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. Without one, development
uses a random key and every sign-in ends when the API restarts; production refuses to start.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

## Commands

| Command | What it does |
| --- | --- |
| `connectly db upgrade` | Apply database migrations |
| `connectly db check` | Confirm the database and PostGIS are reachable |
| `connectly seed` | Load sectors, need categories, indicator definitions and data gaps |
| `connectly ingest list` | Show every known dataset, its status and whether a local copy exists |
| `connectly ingest fetch <key>` | Download a dataset that has a direct download link |
| `connectly ingest load <key> [--file PATH] [--within-state NAME]` | Validate and load any dataset |
| `connectly ingest runs` | Show the ingestion audit log |
| `connectly derive-rollups` / `connectly derive` | Recompute population roll-ups and derived indicators |
| `connectly users create --email E --name N --role R` | Create an account (roles: admin, researcher, company, viewer) |
| `connectly users list` | Show every account |
| `connectly directory import FILE.yaml` | Add or update directory records from a curated file ([format](docs/directory.md)) |
| `pytest` | Run the backend tests (uses `connectly_test`) |

## Repository layout

```
backend/
  connectly/
    api/            FastAPI app and routes
    core/           settings and database connection
    ingest/         pipelines; manifests/ holds one YAML per dataset (source, licence, fields)
    models/         SQLAlchemy models (provenance, geography, sectors, evidence)
    taxonomy/       sectors, need categories, indicator definitions, recorded data gaps
  alembic/          database migrations
  tests/            unit, API and real-data tests
frontend/           Next.js app (sign-in, overview, explorer, data sources, admin)
  public/brand/     official Connectly logo files (do not edit)
docker/             database init script
docs/               milestone reports, data ingestion guide, brand/ (original logo PDF)
data/raw/           downloaded datasets (git-ignored)
```

## Accounts and roles

| Role | Can |
| --- | --- |
| Admin | Everything, including accounts and the audit log |
| Researcher | Read everything; add community claims; review other researchers' claims |
| Company | Read everything; manage its own organisation's solutions |
| Viewer | Read only |

Every page and API endpoint except `/health` and sign-in needs an account. Passwords are
hashed with Argon2id; accounts lock for 15 minutes after 5 wrong passwords. The browser keeps
the session in an httpOnly cookie and never sees the token. Every sign-in and change is
written to the audit log (Admin → Audit log).

## Adding a dataset

1. Write a manifest in `backend/connectly/ingest/manifests/`: source, version, licence and
   the evidence for it, limitations, download link or manual instructions, and field names.
2. `connectly ingest fetch <key>` (or download it by hand), then `connectly ingest load <key>`.
3. The loader stops with a clear message on a missing coordinate system, data outside Nigeria,
   unknown columns or duplicate codes. It repairs invalid shapes and reports every row it rejects.

## Data and licences

Boundaries © GRID3, licensed CC BY 4.0, distributed by
[geoBoundaries](https://www.geoboundaries.org). The Data sources page in the app lists every
dataset, its licence and evidence, its checksum, and every known data gap.

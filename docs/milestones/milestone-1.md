# Milestone 1 — Foundation: database, administrative hierarchy, ingestion, explorer

Completed 10 November 2026.

## Objective

Build the trustworthy base the rest of the platform depends on. That means a PostGIS database where every value carries provenance, a real geographic hierarchy for Nigeria, a repeatable ingestion pipeline, and a working explorer, all at zero cost.

## Dependencies

| Need | Used | Cost |
| --- | --- | --- |
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker or native) | Free |
| Backend | Python, FastAPI, SQLAlchemy, Alembic, GeoPandas, Shapely | Free, open source |
| Frontend | Next.js 16, Tailwind CSS 4, MapLibre GL 6 | Free, open source |
| Boundary data | GRID3 boundaries (CC BY 4.0) via geoBoundaries | Free, openly licensed |
| Paid APIs, map keys, LLMs | None | — |

## What was built

**Database (migration `0001`).** Eleven tables in four groups:

- *Provenance*: `source`, `dataset`, `ingest_run`. Each dataset records version, source date, licence, licence evidence, commercial-use status, limitations, file name, SHA-256 checksum and retrieval time.
- *Geography*: `admin_area` (country → state → LGA → ward) and `place_alias`.
- *Sectors*: `sector` and `need_category`. All eight sectors and 48 need categories from the brief are present; three are marked priority.
- *Evidence*: `indicator` (6 definitions, no values), `observation`, and `data_gap` (13 recorded gaps).

`observation.value_type` only accepts measured, estimated, modelled, derived, assumed or ai_generated. That enforces the brief's rule to separate facts from estimates, assumptions and AI output at the database level.

**Ingestion pipeline (`connectly ingest`).** One YAML manifest per dataset. For each load the pipeline:

1. Checks the coordinate system and reprojects to WGS 84.
2. Rejects data that falls outside Nigeria.
3. Maps fields, or stops and lists the real column names.
4. Repairs invalid shapes and rejects empty ones, reporting each.
5. Fails on duplicate codes.
6. Optionally keeps only areas inside one state.
7. Upserts rows so database IDs stay stable across reloads.
8. Assigns every area to the parent it overlaps most, and stores that overlap share.
9. Flags any area less than 95% inside its parent, and duplicate names under one parent.
10. Records the run.

Identical reloads are skipped. A file that hasn't been downloaded yet is reported as such, not as a failed load.

**Real data loaded.** Nigeria, 37 states and 774 LGAs, all from GRID3 via geoBoundaries (CC BY 4.0, verified from the distributor's metadata). Every LGA lies 100% inside one state. Adamawa has its 21 LGAs. Repeated LGA names (Bassa, Ifelodun, Irepodun, Obi, Surulere) are correctly separated by state.

**API.** Endpoints:

| Endpoint | Returns |
| --- | --- |
| `/health` | Database, PostGIS and migration status |
| `/api/v1/stats` | Counts read live from the database |
| `/api/v1/areas` | Areas, filtered by level, parent or name/alias search |
| `/api/v1/areas/{id}` | Breadcrumbs, provenance and data-gap notices for one area |
| `/api/v1/areas/{id}/children` | Its sub-areas |
| `/api/v1/geojson` and `/api/v1/areas/{id}/geojson` | Simplified map boundaries with attribution |
| `/api/v1/datasets` | Dataset registry |
| `/api/v1/sectors` | Sectors and need categories |
| `/api/v1/data-gaps` | Recorded data gaps |

**Frontend.**

- **Overview:** live database counts only.
- **Explorer:** map and list. Click from country to state to LGA, filter by name, see each area's boundary source, licence and data-gap notices.
- **Data sources:** every dataset with licence, evidence, checksum and limitations, plus all gaps.

## How to run

See the [README](../../README.md): `docker compose up -d`, then `connectly bootstrap`, `uvicorn …`, and `npm run dev`.

## Tests and results

| Check | Result |
| --- | --- |
| Backend tests (`pytest`) | 42 passed: 36 against synthetic test geometry, 6 against the real loaded data |
| Migrations | Upgrade, downgrade and re-upgrade succeed; models and migrations match with no drift |
| Backend lint (`ruff`) | Clean |
| Frontend lint, typecheck, production build | Clean |
| Browser test (headless Chrome) | Opened the explorer at country level, filtered to Adamawa, clicked into it from the list, clicked Fufore on the map, saw both data-gap notices, returned through the breadcrumb. No browser errors. |

The synthetic test geometry is a set of squares used only in the separate `connectly_test` database. It never reaches the real database.

### Defects found and fixed during testing

1. Identical reloads were not being skipped; a registry update erased the stored parameters.
2. Features with a null geometry arrived as a float and crashed the loader.
3. The map drew nothing. MapLibre's web worker failed to load once bundled. The worker is now served from `public/`.
4. The map clipped areas after the side panel changed height. It now resizes with its container.
5. A hover label stayed on screen after clicking an area.
6. A ward dataset without a downloaded file was recorded as "failed". It is now "registered".

## How to verify it yourself

1. `connectly ingest list`: three boundary datasets show `loaded`, and wards show `registered`.
2. `pytest -v`: 42 tests pass. The 6 in `test_real_data.py` need `connectly bootstrap` to have run first.
3. Open http://localhost:3000/explorer, click Adamawa, and count 21 LGAs. Click any LGA: it shows that wards and communities are not loaded yet.
4. Open http://localhost:8000/docs and call `/api/v1/stats`. The numbers match the Overview page.
5. In `psql`: `SELECT key, licence, licence_verified, file_sha256 FROM dataset;` shows the provenance of everything loaded.

## Limitations and outstanding issues

- **Wards not loaded.** GRID3 Operational Wards v4.0 must be downloaded by hand from the GRID3 data hub. Its column names and licence must be confirmed against the real file; the manifest marks the licence as unverified until then.
- **Boundary vintage.** The loaded state and LGA boundaries are GRID3's February 2023 update as packaged by geoBoundaries (December 2023). GRID3's newer operational boundaries can replace them by loading a new dataset and switching the active one.
- **Areas are from the boundary data.** Areas are computed from the boundary shapes, so they can differ from officially quoted figures. Adamawa computes to about 39,940 km².
- **Not yet built.** Authentication, roles, and editing records through the interface are not built. The API is read-only.
- **Untested here.** The Docker Compose setup and the CI workflow were written but not run, because Docker Hub and GitHub Actions are not reachable from the build workspace. The same setup was tested with a native PostgreSQL + PostGIS install.
- **No basemap by default.** That keeps the map free and offline. A free basemap can be added with one environment variable.

## Next: Milestone 2 — community intelligence for Adamawa

1. Load GRID3 wards for Adamawa.
2. Add a `settlement` table and load GRID3 settlement extents and names, with ward linkage.
3. Load GRID3 health facilities and OpenCelliD towers as `facility` points, and GRID3 modelled population.
4. Compute the first derived indicators: distance to nearest health facility and to nearest mapped tower, and facilities per 10,000 modelled people. Each is stored as `derived` with its method.
5. Build community profiles in the explorer, with every value showing its source and type.

Each of these datasets must be downloaded on your machine, since this workspace cannot reach GRID3 or OpenCelliD.

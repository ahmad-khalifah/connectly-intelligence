# Clean-machine re-verification, 11 November 2026

## Why

The platform was completed and pushed on 10 November. On 11 November it was installed again on
a fresh machine, with nothing carried over from the first build, following the README exactly.
The aim was to confirm the completion report's claims and find anything the first build missed.

## Environment

- Ubuntu 24.04, Python 3.13, Node.js 22, PostgreSQL 16.15 + PostGIS 3.4.2 (GEOS 3.12)
- Install path: README "Development setup", using the "Without Docker" database instructions.
  The build environment cannot reach Docker Hub, so the Docker path was not run here. It was
  verified on 10 November by the CI `stack` job.
- Network: only GitHub and package registries are reachable. GRID3, HDX, OpenCelliD,
  Geofabrik, the DHS API and Docker Hub are still blocked, so no new external datasets could
  be loaded.

## Results

| Check | Result |
| --- | --- |
| `connectly bootstrap` on an empty database | Passed in 35 s: 1 country, 37 states, 774 LGAs, 9,308 wards, modelled ward population, roll-ups; indicators with no source data were skipped and reported, not filled |
| Backend tests | 155 passed (152 existing + 3 new) |
| `ruff check`, `ruff format --check`, `alembic check` | Clean; no migration drift |
| Frontend lint, type check, unit tests (3), production build | Pass |
| Browser tests (Playwright, 8) against the production build | Pass, run twice: once after the fixes below, once on a freshly bootstrapped database |
| `pip-audit` | No known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities. The full audit reports 8 moderate findings in `minimatch`, used only by the ESLint toolchain at development time and not shipped in the app. |
| Logo fidelity | The in-app SVGs were compared with a fresh `pdftocairo` conversion of the supplied PDF (same checksum as the file attached on 11 November). Every shape and both colours match; only the PDF's white page background is omitted. |
| Brand in the browser | Logo checked on the sign-in page, navigation, dashboard, explorer, mobile layout and PDF report |

## Defects found and fixed

1. **Neighbouring areas overlapped on the map.** The map API simplified each boundary on its
   own, so a shared border moved differently on each side. Neighbours then overlapped in thin
   slivers and left gaps. The worst case was Mubi North and Hong in Adamawa: a sliver 27 km
   long at LGA level, with 0.24 km² overlaps elsewhere. The stored boundaries were correct
   throughout; only the drawn shapes were affected.
   - **Fix:** all areas in a map layer are now simplified together as one coverage, using
     Shapely's `coverage_simplify`, so each shared border stays identical on both sides. It
     runs in the API, so it does not depend on the server's PostGIS or GEOS version.
   - **Result:** zero overlap measured for the national state layer, the Adamawa LGA layer
     and all 226 Adamawa wards. Payloads are 328 KB, 68 KB and 218 KB, served in 0.02–0.2 s.
   - **Tests:** `backend/tests/test_map_simplification.py`.

2. **A dark wedge drawn across Mubi North at state zoom.** This was traced to MapLibre's
   polygon triangulation, not to the data. The polygon is valid, has no narrow necks, and draws
   the same wedge in a bare MapLibre page, in MapLibre 5.24 as well as 6.17, and with MapLibre's
   own simplification turned off. The triangulation draws a sliver of the area twice. With the
   80% opaque fill, the double-drawn part showed through as a darker wedge.
   - **Fix:** on the default plain background, area fills are now opaque, which makes a
     double-drawn sliver invisible. Hover is shown as an outline, and choropleth borders are
     white so that neighbours in the same colour class stay distinct.
   - **Remaining limitation:** if an optional basemap is configured
     (`NEXT_PUBLIC_BASEMAP_STYLE_URL`), fills stay translucent so the basemap shows through,
     and the wedge can reappear at some zoom levels.

3. **Browser tests left a test organisation active.** The directory test retired its solution
   but not its organisation. It now retires both, as `frontend/e2e/README.md` describes.

## Not re-verified here

- **Docker Compose stack.** Docker Hub is unreachable from this environment. It was verified
  by CI on 10 November; the changes above do not touch the Dockerfiles or the Compose file.
- **The GitHub Actions run for this push.** The Actions API is not reachable from here.
  Check the Actions tab after pulling.

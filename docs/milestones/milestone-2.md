# Milestone 2: Wards, population and the community intelligence database

Completed 10 November 2026.

## What was built

- **Ward boundaries, loaded automatically.** All 9,308 GRID3 wards (April 2022, CC BY 4.0) come from geoBoundaries' geoContrast archive, and the publisher's Git LFS checksum is verified on download. Checks:
  - every ward lies 100% inside one LGA;
  - every ward's GRID3 state code matches the state it lies in;
  - GRID3's codes for Borno (`BR`) and Kebbi (`KB`) are mapped explicitly, because they differ from ISO.
- **Modelled population.** Ward values are stored with their 95% interval. They are labelled modelled and unverified, because the source attribution is inferred (see `docs/data-ingestion.md`). They sum to identical totals at ward, LGA and state level.
- **Community tables.** Migration `0002` adds:
  - `settlement`: points and extents;
  - `facility`: health, education, financial, telecom, energy, market, transport, agriculture, community;
  - `claim`: qualitative facts entered by researchers, each with a source;
  - interval bounds and a uniqueness rule on `observation`.
- **Generic ingestion.** Every manifest kind loads through `connectly ingest load`:
  - boundaries;
  - point and extent files: GeoJSON, GeoPackage, Shapefile, CSV, CSV.gz and zip;
  - OpenStreetMap extracts, mapped to facility kinds by tag rules;
  - typed-in statistics tables, validated as a whole file;
  - the DHS Program API, which checks each indicator's label.
- **Download safety.**
  - Publisher checksums are verified.
  - Exactly one named archive member is extracted, and unsafe member paths are refused.
  - A changed manifest forces a reload.
- **Derivation engine (`connectly derive`).** It computes ten indicators: density, facilities per 10,000 people, distance to the nearest facility, and the share of settlements more than 5 km from care. It:
  - only computes inside each dataset's geographic coverage;
  - excludes facilities marked non-functional, and pharmacies;
  - replaces its earlier output, so reruns are idempotent;
  - gives the reason for every indicator it skips.
- **Community profiles and API.**
  - `/areas/{id}/profile` lists each field with dataset, period, value type and verification status. State or LGA values appear only as labelled context, and missing indicators are listed explicitly.
  - `/choropleth` shows values for one level only and lists areas without a value.
  - Also added: `/indicators`, `/facilities`, `/geojson/points` and `/settlements/{id}`, which includes the nearest facility of each kind within 50 km.

## Real data in the development database

| Item | Count |
| --- | --- |
| Areas | 1 country, 37 states, 774 LGAs, 9,308 wards |
| Observations | 29,546: population at three levels, density at three levels, urban flag |
| Facilities, settlements | 0 (need local download, see `docs/data-ingestion.md`) |

## Tests

73 backend tests pass. They cover:

- every loader, using synthetic GeoJSON, GeoPackage, gzipped CSV, OSM XML and DHS JSON;
- the coverage rule, idempotent derivation, and atomic table validation (one bad row loads nothing);
- checksum mismatch and unsafe archive paths;
- the profile and API endpoints;
- six checks against the real loaded data.

## Defects found and fixed

1. Inserts written in raw SQL skipped Python-side defaults. The `verification_status` defaults now live in the database.
2. Reloading skipped files whose manifest had changed. The manifest's checksum is now part of the reload check.
3. GRID3 state codes are not ISO codes for Borno and Kebbi. An explicit map was added, after confirming every affected ward's location.
4. CI ran on the official PostGIS image, which has extension tables the local install lacks; the schema-drift test reported them as drift. The test now ignores tables the application doesn't own.

## Limitations

- Settlements, facilities, DHS, EFInA and NCC data are not loaded here, because the build environment cannot reach their hosts. Each has a manifest, a tested loader and exact instructions.
- Distance from a ward's centre is a coarse proxy. It is replaced by settlement-level measures once settlements are loaded.

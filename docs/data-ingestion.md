# Data ingestion guide

Every dataset Connectly uses is described by a manifest in
`backend/connectly/ingest/manifests/`. The manifest records the source, version, licence (and
the evidence for it), limitations, download method and field mapping. Loaders copy it into the
`dataset` table, so every value in the database can be traced to a file, a checksum and a licence.

**Rules the pipelines enforce**

- Nothing is typed in or generated. Values come from a file, a published table (with a page or
  table reference on every row), the DHS API, or a documented computation (`derived`).
- A dataset whose licence has not been read on the publisher's page is marked
  `licence_verified: false` and `commercial_use_allowed: null`. A manifest cannot allow
  commercial use on an unverified licence.
- Values measured for a large area (a state survey) are never assigned to smaller areas.
- Derived values are computed only inside the area a dataset covers. A health facility file
  loaded for Adamawa alone never produces "0 clinics" for Kano.
- Reloading an identical file with an identical manifest is skipped. Changing the manifest
  forces a reload.

## 1. Loaded automatically by `connectly bootstrap`

These download directly from GitHub-hosted mirrors with recorded checksums.

| Manifest key | What | Records | Licence | Source |
| --- | --- | --- | --- | --- |
| `geoboundaries-nga-adm0` | National boundary | 1 | CC BY 4.0 (verified) | GRID3 via geoBoundaries gbOpen |
| `geoboundaries-nga-adm1` | States + FCT | 37 | CC BY 4.0 (verified) | GRID3 via geoBoundaries gbOpen |
| `geoboundaries-nga-adm2` | LGAs | 774 | CC BY 4.0 (verified) | GRID3 via geoBoundaries gbOpen |
| `geocontrast-grid3-nga-wards-2022` | Wards (April 2022), urban flag, modelled population | 9,308 | CC BY 4.0 (verified) | GRID3 via geoBoundaries geoContrast |

Checks run on these files (all pass on the current data):

- every LGA lies at least 95% inside one state (actual: 100%);
- every ward lies at least 95% inside one LGA (actual: 100%);
- every ward's GRID3 state code matches the state it lies in (GRID3 uses `BR` for Borno and
  `KB` for Kebbi where ISO 3166-2 uses `BO` and `KE`; the manifest maps them explicitly);
- modelled population sums to the same total at ward, LGA and state level (216,597,461).

**About the ward population values.** The ward file contains columns `mean`, `q025`, `q50`,
`q975`. Their names and structure match the ward summaries of WorldPop and the National
Population Commission's *Bottom-up gridded population estimates for Nigeria, version 2.0*
(CC BY 4.0, representative of about 2019), which were published on GRID3 ward boundaries. The
file itself does not say so, and the GRID3 page could not be checked from the build
environment. The values are therefore stored as **modelled** and **unverified**. To confirm,
download WorldPop's v2.0 ward summary and compare a few wards; then mark the dataset verified.

After loading, `bootstrap` also runs:

- `connectly derive-rollups`: sums ward population to LGA and state (derived; intervals are
  not summed, because they are not additive).
- `connectly derive`: computes every derived indicator whose inputs are loaded and reports the
  reason for each one it skips.

## 2. Download on your machine, then load

The build environment could not reach these hosts, so each must be downloaded locally. Put
manual downloads in `data/manual/` (git-ignored). `--within-state Adamawa` keeps only records
inside Adamawa; omit it to load the whole country.

### Boundaries and settlements (GRID3)

| Manifest key | File to download | Where | Command |
| --- | --- | --- | --- |
| `grid3-nga-wards-v4` | GRID3 NGA – Operational Wards v4.0 (GeoJSON or GeoPackage) | [data.grid3.org](https://data.grid3.org/datasets/GRID3::grid3-nga-operational-wards-v4-0/about) | `connectly ingest load grid3-nga-wards-v4 --file data/manual/<file> --activate yes` |
| `grid3-nga-settlement-names` | GRID3 NGA – Settlement Names | [data.grid3.org](https://data.grid3.org/search?q=Nigeria%20settlement%20names) | `connectly ingest load grid3-nga-settlement-names --file data/manual/<file> --within-state Adamawa` |
| `grid3-nga-settlement-extents` | GRID3 NGA – Settlement Extents v4.1 | [data.grid3.org](https://data.grid3.org/search?q=Nigeria%20settlement%20extents) | `connectly ingest load grid3-nga-settlement-extents --file data/manual/<file> --within-state Adamawa` |

GRID3 licences are listed on each dataset page. Read it, then set `licence`,
`licence_verified: true`, `licence_evidence` and `commercial_use_allowed` in the manifest.

### Facilities

| Manifest key | File | Where | Licence | Command |
| --- | --- | --- | --- | --- |
| `grid3-nga-health-facilities` | GRID3 NGA – Health Facilities v3.0 (24 states) or v2.0 (all states) | [data.grid3.org](https://data.grid3.org/search?q=Nigeria%20health%20facilities) | Confirm on page | `connectly ingest load grid3-nga-health-facilities --file data/manual/<file> --within-state Adamawa` |
| `grid3-nga-education-facilities` | GRID3 Nigeria Education Facilities (Dec 2020) | [HDX](https://data.humdata.org/dataset/nigeria-education-facilities) | CC BY (confirm) | `connectly ingest load grid3-nga-education-facilities --file data/manual/<file> --within-state Adamawa` |
| `opencellid-nga` | `621.csv.gz` (Nigeria, MCC 621) | `https://opencellid.org/ocid/downloads?token=YOUR_TOKEN&type=mcc&file=621.csv.gz` (free registration for a token) | CC BY-SA 4.0 (verified) | `connectly ingest load opencellid-nga --file data/manual/621.csv.gz --within-state Adamawa` |
| `osm-nga-geofabrik` | `nigeria-latest.osm.pbf` (~1 GB) | Direct: `connectly ingest fetch osm-nga-geofabrik` | ODbL 1.0 (verified) | `connectly ingest load osm-nga-geofabrik --within-state Adamawa` |

If a GRID3 file's column names differ from the manifest's candidates, the loader stops and
prints the real column names. Add the right name to `fields:` in the manifest and run again.

OpenCelliD records are individual cells. Records at the same rounded position (4 decimal
places, about 11 m) with the same radio technology are collapsed into one site.

### Statistics

| Manifest key | What | How |
| --- | --- | --- |
| `dhs-ng-2023-state` | NDHS 2023-24 state indicators (electricity, mobile phone, facility births, women's literacy) | `connectly ingest fetch dhs-ng-2023-state && connectly ingest load dhs-ng-2023-state`. Each indicator id is checked against its returned label; a mismatch stops the load. |
| `efina-a2f-2023-state` | EFInA A2F 2023 state financial inclusion | Copy `backend/connectly/ingest/templates/state_indicator_template.csv` to `data/manual/efina-a2f-2023-state.csv`, fill one row per state from the report with a page/table reference, then `connectly ingest load efina-a2f-2023-state --file data/manual/efina-a2f-2023-state.csv` |
| `ncc-internet-subscriptions-state` | NCC active internet subscriptions by state | Same template; `connectly ingest load ncc-internet-subscriptions-state --file <file>` |

A typed-in table loads only if **every** row is valid: a known state, an allowed indicator, a
number in range, and a source reference. One bad row stops the whole file.

### After loading anything

```bash
connectly derive        # recompute derived indicators
connectly ingest list   # status of every dataset
connectly ingest runs   # audit log of loads, with warnings and errors
```

## 3. Adding a new dataset

1. Copy the closest manifest in `backend/connectly/ingest/manifests/` and change it.
2. Record the licence only after reading it on the publisher's page, with the evidence.
3. Load with `--within-state` first and read the notes it prints.
4. Add a test with a small synthetic file in `backend/tests/` if the manifest uses a new option.

## 4. Known data gaps

The app lists every recorded gap on its Data sources page (`/data`). Gaps include: no census
since 2006; no open register of agent banking or mobile money agents; operator coverage maps
not open; speed-test data non-commercial only; school data dated December 2020; crop
production by LGA not open; current settlement electrification unconfirmed; no open directory
of technology solutions; and community economic activities requiring field verification.

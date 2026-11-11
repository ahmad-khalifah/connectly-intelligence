# Nationwide coverage, 11 November 2026

## Objective

Connectly Intelligence covers all of Nigeria: 36 states and the FCT, all 774 LGAs, wards
nationwide, settlements wherever reliable data exists, and all eight sectors. Adamawa was the
first validation state only. This milestone removed every place where the application depended
on Adamawa, and closed two gaps that would have shown partial data as nationwide.

## What was already national

- Boundaries for the country, 37 states, 774 LGAs and 9,308 wards, loaded by `bootstrap`.
- Modelled population for every ward, rolled up to LGAs and states.
- Sectors, indicators, needs assessment, matching and market entry, which take any area as
  input.

## Problems found and fixed

| # | Problem | Effect before the fix | Fix |
| --- | --- | --- | --- |
| 1 | A national facility or settlement file was recorded as covering all 37 states. | Loading GRID3 Health Facilities v3.0 (24 states) nationally would have given the other 13 states "0 facilities per 10,000 people" instead of "no data". | Coverage is the publisher's declared state list (`coverage_states`), the `--within-state` state, or the states where the file has records. It is never assumed. Each load prints its coverage and the states it does not cover. |
| 2 | Several datasets of one kind were combined by intersecting their coverage and counting all their records. | GRID3 v3.0 + v2.0 would have covered only 24 states and double-counted clinics there. GRID3 + OpenStreetMap would have double-counted too. | One dataset per state: the lowest `priority`, then the newest publication. The choice is stored with each derived dataset (`sources_by_state`). |
| 3 | Activating a new ward or LGA file replaced that level everywhere. | A partial ward release, or one loaded with `--within-state`, would have removed the wards of every other state. | Activation is limited to the states the file covers. Other states keep their areas, and facilities and settlements are re-linked. |
| 4 | The dashboard was built around a hard-coded `FOCUS_STATE = "Adamawa"`. | The overview presented one state. | A national card and a **Data coverage by state** table: every state × every layer, with the source used and dashes where no data exists. Backed by `/api/v1/coverage`. |
| 5 | The Needs page defaulted to Adamawa, and LGAs could only be compared within one state. | National comparison was not offered. | LGAs default to all 774 across Nigeria. Ward comparisons ask for a state; none is assumed. |
| 6 | Load instructions in seven manifests said `--within-state Adamawa`. | National loading looked like the exception. | National loads are the documented default; `--within-state` is for trial runs. |
| 7 | Two recorded data gaps were scoped to "Adamawa State". | National gaps looked local. | Rescoped to Nigeria. |

The GRID3 health facility manifest was split into `grid3-nga-health-facilities-v3` (24
declared states, priority 10) and `-v2` (all states, priority 20). All 24 declared names
resolve to distinct loaded states.

A national LGA map of 774 areas is simplified more coarsely (0.005°, invisible at national
zoom). It reaches the browser gzip-compressed at about 395 KB.

## Guard against regressions

`backend/tests/test_no_hardcoded_states.py` fails if any backend module or web-app source file
uses a state name as a literal value. Docstrings, comments and dataset manifests are allowed.
One legitimate exception is allow-listed: "Edo" as a language name.

## Tests

- `backend/tests/test_national_coverage.py`, 6 tests:
  - a national file covers only the states with records;
  - declared coverage wins, and records outside it are flagged;
  - an unknown declared state stops the load;
  - overlapping sources are not double-counted, and each state uses one source;
  - a partial LGA release activates only in its own state;
  - the coverage endpoint reports per state.
- Hard-coding guard: 2 tests.
- Backend total: 163 passed. Frontend lint, type check, unit tests and build: pass.
- Browser tests: 8 passed against a freshly bootstrapped database. They now check the national
  card, the 37-row coverage table, the national LGA default and the ward prompt.

## Current coverage, from the coverage table

| Layer | States covered |
| --- | --- |
| Ward boundaries | 37 / 37 |
| Modelled population | 37 / 37 |
| Health facilities, schools, mobile sites, financial access points, markets, settlements, state statistics | 0 / 37 until the national files are loaded (see `docs/data-ingestion.md`) |

## Expanding across Nigeria

No code change is needed. Download each national file, load it without `--within-state`, run
`connectly derive`, and check the coverage table. Any state a file does not cover stays
visibly uncovered until another dataset fills it.

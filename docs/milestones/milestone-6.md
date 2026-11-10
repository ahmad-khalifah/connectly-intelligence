# Milestone 6: Needs assessment and gap scoring

Completed 10 November 2026.

## What was built

- **Gap scoring engine** (`services/needs.py`), with indicator models for six sectors. The full method is in `docs/methodology.md`. It works as follows:
  - areas are ranked against comparable areas within the same scope;
  - an indicator is used only if at least 3 areas in scope have a value;
  - indicators measured only for larger areas are excluded, with the reason given;
  - the score is a weighted mean of percentiles;
  - coverage and confidence are reported, and no score is given below 34% coverage;
  - every score comes with plain statements generated from the numbers.
- **API:**
  - `GET /needs/models`;
  - `GET /needs/assessment?sector&level&scope_id`;
  - `GET /needs/areas/{id}`, which gives one area's scores in every sector against similar areas in its state;
  - `GET /geojson?within_id=` (for example, all wards of a state).
- **Needs page.**
  - Choose a sector and compare all states, or the LGAs or wards of one state.
  - It shows the evidence used, with weights and the reason any indicator was not used.
  - The areas are shown on a map coloured by score.
  - A ranking lists each area's score, confidence and population. Each entry expands to show its evidence statements and what data is missing.
- **Method page** at `/needs/method`, showing the method and the weights read from the live models.
- **Community profiles.** A "Technology access gaps" panel shows the area's score, rank and confidence per sector, with its strongest evidence statement.

## Results on the data loaded here

None. Every sector model depends on facility, settlement or survey data, and that data must be downloaded locally (`docs/data-ingestion.md`). The app therefore reports "not enough data loaded to score" everywhere. That is the correct result, not a fault.

Agriculture and transport have no open indicator at all, and say so.

To check the interface, temporary synthetic values were inserted for Adamawa LGAs and removed afterwards. That visual check covered the ranking, map, confidence labels, evidence statements and profile panel.

## Tests

- **Backend:** 129 tests pass (7 new). They cover:
  - percentiles with ties;
  - a full worked example with hand-computed scores, coverage and confidence;
  - excluding indicators that are measured only at state level;
  - giving no score when too few areas have data;
  - sectors with no model;
  - scope validation;
  - the API, including authentication;
  - boundaries within any ancestor area.

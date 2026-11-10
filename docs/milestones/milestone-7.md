# Milestone 7: Technology matching engine

Completed 10 November 2026.

## What was built

- **Matching engine** (`services/matching.py`). It covers all eight criteria in the brief: relevance, suitability, geographic availability, affordability, internet and device requirements, language, distribution and implementation feasibility.
  - Each criterion is scored from structured directory fields and area evidence:
    - indicators for the area, or its state as labelled context;
    - languages recorded by researchers;
    - facilities recorded in the area;
    - coverage records.
  - A criterion is "unknown" when the data it needs is missing.
  - The method and weights are in `docs/methodology.md`.
- **Target needs.**
  - The user can choose a need, or the engine derives needs from the area's gap evidence.
  - With neither, the user is asked to choose a need; the engine does not match on sector alone.
  - Solutions in the same sector that do not address a target need are listed separately as "not recommended", with the reason.
- **Results.** Each result has:
  - a score, a confidence level and how many of the eight criteria could be judged;
  - its availability;
  - "why it fits" and "check before acting" lists;
  - the reason and evidence for every criterion.
- **API:** `POST /api/v1/matching {area_id, sector, need?, target_groups?, max_price_ngn?}`.
- **Matching page.**
  - Pick a state, LGA and ward, a sector, and optionally a need, target groups and a price ceiling.
  - Results appear as explained cards.
  - "Find solutions" links from each sector on community profiles open the page pre-filled and run the match.

## Data

The directory is empty (see Milestone 4), so matching returns "no published solution addresses these needs" until records are added.

To check the interface, two synthetic records were imported and the page was viewed. The records were then deleted, together with their audit entries.

## Tests

- **Backend:** 133 tests pass (4 new). A synthetic scenario covers:
  - needs derived from gap evidence;
  - the exclusion of same-sector solutions that do not address the target needs;
  - unpublished and other-sector solutions not being considered;
  - per-criterion scores worked out by hand: language match against mismatch, unknown coverage, price against the ceiling, a smartphone caveat, feasibility arithmetic;
  - lower confidence for thinner records;
  - an explicitly chosen need;
  - the prompt to choose a need when there is no evidence;
  - unknown languages;
  - input validation.

# Milestone 8: Market entry intelligence

Completed 10 November 2026.

## What was built

- **Analysis** (`services/market_entry.py`, `POST /api/v1/market-entry`). It takes the brief's inputs:
  - industry, product and target beneficiaries;
  - pricing, expansion objective and budget;
  - preferred location;
  - optionally, an existing directory record instead of a product description.
- **Candidate ranking.** Candidates are the LGAs of the preferred states, or all states. Each opportunity score combines gap, fit, reach and competition (see `docs/methodology.md`). An area with no evidence of need is listed but not scored or recommended.
- **The brief's twelve outputs:**
  1. suitable areas;
  2. beneficiary segments;
  3. demand (always a data gap, with reach shown separately);
  4. competing solutions;
  5. community organisations;
  6. institutional partners (recorded facilities and directory organisations that list partnership interests);
  7. distribution channels;
  8. local languages;
  9. communication strategies;
  10. user acquisition;
  11. implementation risks;
  12. a recommended entry strategy.

  Every finding is tagged as fact, derived, recommendation or data gap. Recommendations come from stated rules applied to the evidence shown, never from a model.
- **Market entry page.**
  - A form with an optional directory record, product requirements, languages, channels, target groups, price, objective, budget and preferred states.
  - Results show a candidate table and the twelve sections, each item tagged.

## Defect found during the walkthrough

The first version ranked Adamawa's LGAs even though no health data was loaded. Ranking was then driven only by population and by a "fit" value that included whether the record was verified. As a result it recommended "run a pilot in Fufore" with nothing to show a need there.

This was fixed in two ways:

- an area now needs evidence of need before it gets a score or a recommendation;
- fit now measures local conditions only.

A test covers the fix.

## Tests

- **Backend:** 137 tests pass (4 new). They cover:
  - a full in-state analysis: ranking by evidence, all twelve sections in order, demand as a data gap, competitors, languages, the budget caveat, the strategy, and that only the four kinds of finding are used;
  - an analysis from a directory record nationally;
  - no recommendation without evidence of need;
  - input validation.
- **Frontend:** lint, type check and production build pass. Browser walkthrough with the Adamawa data that is loaded.

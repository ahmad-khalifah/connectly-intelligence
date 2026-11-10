# Methods

This page explains how Connectly Intelligence turns loaded data into scores and
recommendations. Everything here is a deterministic calculation over the database. No language
model is involved unless a section explicitly says so.

## Value types and verification

Every value is stored with one of the following **value types**:

| Value type | Meaning | Example |
| --- | --- | --- |
| *measured* | Counted or surveyed | A DHS survey percentage |
| *modelled* | Produced by a statistical model | WorldPop population |
| *derived* | Computed here from other values, listing its inputs | Facilities per 10,000 people |
| *estimated* | An estimate | |
| *assumed* | An assumption | |
| *ai_generated* | Produced by a language model; never used in scores | |

Every value also has a **verification status**: *unverified*, *source_verified*,
*field_verified*, *disputed* or *retired*.

A value measured for a larger area (for example a state survey) is shown on smaller areas only
as labelled context. It is never treated as the smaller area's own value.

## Needs assessment (gap scores)

Code: `backend/connectly/services/needs.py`. Indicators and weights:
`backend/connectly/taxonomy/need_models.py`.

1. **Scope.** All areas of one level inside one larger area: the states of Nigeria, or the
   LGAs or wards of one state.
2. **Ranking.** For each indicator in the sector's model, the areas in scope that have a value
   measured at their own level are ranked. Values for larger areas are the same across the
   scope, so they cannot separate the areas and are not used. An indicator is used only if at
   least 3 areas in scope have a value.
3. **Percentile.** Each area gets a deprivation percentile from 0 to 100, where 100 means the
   least served in scope. Tied values share the average rank. Direction comes from the
   indicator's `higher_is_worse` flag.
4. **Score.** The gap score is the weighted mean of the percentiles available for the area.
5. **Coverage.** Coverage is the share of the model's total weight that is available for the
   area. Below 34% coverage, no score is given ("insufficient data").
6. **Confidence.** Confidence = coverage × the weighted quality of the values used.
   - Quality by value type: measured 1.0, derived 0.85, modelled 0.7, estimated 0.6,
     assumed 0.3, AI-generated 0.
   - Quality is then multiplied by 0.9 if the value is unverified, or 0.5 if it is disputed.
   - Confidence labels: high is 0.6 or more, medium is 0.35 or more, otherwise low.
7. **Evidence statements.** Every score is explained by plain statements generated from the
   numbers, for example "Health facilities per 10,000 people: 0.3 (lower is worse); worse
   than 95% of LGAs in Adamawa with data (median 1.91)". Each statement also shows the value
   type, verification status, period and dataset.

Scores are **relative**: a high score means "less served than most comparable areas on the
evidence loaded". They are not an absolute measure of need, and they change as data is added.

Agriculture and transport have no open indicator loaded, so they are not scored. The app says
so; it does not guess.

## Technology matching

Code: `backend/connectly/services/matching.py`.

**Which solutions are considered.** Only published solutions from approved organisations, and
only those that address one of the *target needs*. The target needs are either:

- the need the user chose, or
- the needs linked to indicators where the area is worse than at least half of comparable
  areas (`INDICATOR_NEEDS`).

If neither applies, the user is asked to choose a need. Solutions in the same sector that do
not address a target need are listed as "not recommended", with that reason. Products are never
recommended for being in the same sector alone.

**Criteria.** Each criterion scores from 0 to 1, or is *unknown* when the data it needs is
missing. Unknown criteria are left out of the score and lower the confidence. They never count
as a pass or a fail.

| Criterion | Weight | How it is judged |
| --- | --- | --- |
| Relevance | 20% | 0.85 for one target need addressed, 1.0 for two or more |
| Suitability | 10% | Target groups against beneficiary groups (1.0 if they overlap, 0.2 if not). Literacy needed against women's literacy (DHS, state level). |
| Availability | 15% | Nationwide or operates here 1.0; operates in part of the area 0.7; plans to expand here 0.4; not available 0.1; coverage not stated is unknown |
| Affordability | 10% | With a price ceiling: lowest price ≤ ceiling 1.0, ≤ 2× ceiling 0.5, otherwise 0.1. Without one, the pricing model: free or donor-funded 1.0, freemium 0.8, pay per use, pay-as-you-go or contract 0.7, subscription 0.5, one-off purchase 0.4. No open income data exists to judge local ability to pay. |
| Internet and devices | 15% | Internet requirement against distance to the nearest recorded mobile site: up to 5 km 1.0, up to 15 km 0.6, beyond that 0.3. 4G needs a site within 3 km. Device requirement against household phone ownership (smartphone ownership is not measured, so that share is scaled by 0.6). |
| Language | 10% | Languages supported against languages recorded for the area: overlap 1.0; no overlap 0.2, or 0.4 with voice or audio features. Unknown when either side is missing. |
| Distribution | 10% | Best usable channel: a channel scores 1.0 when the facilities it relies on (health facilities, schools, financial points, mobile sites, markets) are recorded in the area. Direct sign-up depends on connectivity. Partner channels cannot be measured. |
| Feasibility | 10% | Power requirement against household electricity access; provider presence; whether the record has been verified |

**Score and ranking.**

- Score = weighted mean over the criteria that are known, × 100.
- Confidence = the weight of known criteria × 1.0 if the record is verified, or × 0.8 if it
  is not. Labels: high is 0.7 or more, medium is 0.45 or more, otherwise low.
- Ranking orders by score × (0.5 + 0.5 × confidence), so a well-evidenced match ranks above
  a thinly evidenced one with a similar score.

Every result lists its strengths (criteria scoring 0.8 or more) and the points to check before
acting (criteria under 0.5, or unknown). Each criterion shows its reason and its evidence.
Matches are suggestions drawn from directory records, not endorsements.

## Market entry

Code: `backend/connectly/services/market_entry.py`.

**Candidate areas.** The LGAs of the preferred states, or all states when no state is
chosen. A product's requirements come from a directory record or from the form.

**Opportunity score.** For each candidate, a weighted mean over the parts with data:

| Part | Weight | What it measures |
| --- | --- | --- |
| Gap | 40% | The area's needs-assessment score for the sector |
| Fit | 25% | Local conditions, from the matching criteria: internet and devices, language, distribution, and electricity access against the product's power needs |
| Reach | 20% | The area's population percentile among the candidates. This is modelled population, not demand. |
| Competition | 15% | 1 ÷ (1 + the number of published solutions for the same need operating there) |

**An area without evidence of need gets no score.** Ranking by population and conditions
alone would only rank areas by size, so such areas are listed for reference and not
recommended.

**Report sections.** The report covers the brief's twelve items, each finding tagged:

- *fact* (from the database, with its source);
- *derived* (computed from facts);
- *recommendation* (a stated rule applied to the evidence shown, for example "women's literacy
  below 50% → use voice and demonstration");
- *data gap*.

Market demand, customer numbers, partnerships and costs are never estimated: no open data
supports them. The budget is recorded but not compared with costs.

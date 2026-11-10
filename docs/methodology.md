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

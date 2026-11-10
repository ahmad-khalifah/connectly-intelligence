# Milestone 5: Explorer, community profiles and community information

Completed 10 November 2026.

## What was built

- **Explorer.** Users move from country to state, LGA and ward.
  - **Colour by indicator.** The map colours the smaller areas by any indicator that has values at that level. The colour scale runs from cream through gold to maroon, using the brand palette with lightness that steadily increases.
    - Classes are quintiles of the areas shown, and repeated breaks are merged.
    - Areas without a value appear grey and are counted in the legend. They are never coloured with a parent's value.
    - The legend states the value type, verification status, period and dataset.
  - **Sector filter.** It narrows the indicator list and the facility layer to that sector's facility type, for example health facilities or mobile network sites. Indicators with no values at the current level are listed but cannot be selected.
  - **Facility and settlement points.** These layers are available at state level and below. Hovering shows details; clicking a settlement opens its page.
  - **Area list.** It shows each area's value for the chosen indicator.
  - **Mobile.** The map appears first on small screens.
- **Community profiles** (`/areas/{id}`) for any state, LGA or ward. The ward stands in for "community" until settlement data is loaded. They cover the 18 community fields in the brief:
  - name, state, LGA, coordinates, area and population, including the 95% interval and value type;
  - urban or rural classification;
  - one panel per sector, with facility counts. These say explicitly when no facility data is loaded for the state, which is different from zero.
  - indicators for the area itself, and state or LGA figures labelled as context;
  - claims entered by researchers;
  - for each sector, a list of indicators that are not available;
  - data sources with licences, known data gaps, and the last-updated date.
  - Smaller areas are listed with links.
- **Settlement pages** (`/settlements/{id}`). Each shows the record and its source, the nearest facility of each type within 50 km (straight-line distance), and community information.
- **Community information.** Researchers can:
  - add facts with a source, how they are known and when they were observed;
  - mark languages from the ISO 639 list;
  - edit their own facts, which then go back for review;
  - review other researchers' facts (checked against source, confirmed in the field, or disputed);
  - retire facts and see each fact's full history.
  - The forms warn against entering personal details, and the API refuses phone numbers and e-mail addresses.
- **Area notice fix.** The "settlements not loaded" notice is now shown only for areas that actually have no settlements.

## Tests

- **Backend:** 122 tests pass. The profile test now also checks the author of each claim.
- **Frontend:** lint, type check and production build pass.
- **End to end:** browser walkthrough of:
  - the country map;
  - Adamawa LGAs coloured by modelled density with a five-class legend;
  - Demsa wards coloured by population, with the facility layer on;
  - the profile for Bille ward: 12,867 people (95% interval 8,342–19,288), labelled modelled and unverified;
  - adding a languages entry through the form;
  - the explorer on mobile.
  - The browser-test entry was deleted afterwards.

## Limitations

- Sector panels show facility counts and indicators only for data that is loaded. In this build that is boundaries and population, because facility, settlement and survey files need local downloads (`docs/data-ingestion.md`).
- Distances are straight-line, not travel time. No open road-network travel model is integrated.

# Milestone 4: Technology solutions directory

Completed 10 November 2026.

## What was built

- **Data model** (migration `0004`): `organisation`, `solution`, `solution_need` and `solution_coverage`. All 20 company fields from the brief are covered; see `docs/directory.md`.
- **Structured requirements.** The fields the matching engine compares are fixed vocabularies, not free text:
  - internet, device, electricity and literacy requirements;
  - languages (ISO 639);
  - beneficiary groups, distribution channels, accessibility features and partnership types.
  - An empty field means not known.
- **Coverage.** A solution can be nationwide, or cover chosen states, LGAs or wards, each marked "operating" or "expansion interest". Availability in any area is computed through the boundary hierarchy, with six possible results:
  - nationwide;
  - operates here;
  - operates in part of this area;
  - plans to expand here;
  - not available;
  - coverage not stated.
- **Workflow.**
  - Solutions move through draft, awaiting review, published, rejected and retired.
  - Admins approve organisations and publish solutions.
  - Company accounts register their own organisation, add solutions and submit them.
  - A company's edit to a published solution sends it back for review.
  - Admins mark records as checked against the source, verified in the field, or disputed, and must say what was checked.
  - Every change is in the audit log.
- **Visibility.** Other users only see published solutions from approved organisations. Drafts are visible only to admins and to the owning company.
- **Batch import:** `connectly directory import FILE.yaml`. It validates every record before writing anything, resolves state and LGA names to boundaries, and updates records on re-import.
- **Language claims.** Researchers' "languages spoken" claims now carry ISO 639 codes, so matching can compare them with the languages a solution supports.
- **Web app.** Directory pages:
  - search, with filters by sector and by availability in a state;
  - solution and organisation pages with every field, "Not known" for empty fields, and the source;
  - forms for organisations and solutions, including a coverage picker by state and LGA;
  - review actions for admins and the company workflow.

## Data

The directory is empty. No open register of Nigerian technology solutions exists (recorded as a data gap), and no records were invented. Admins and companies add records, each with its source.

## Tests

- **Backend:** 122 tests pass (19 new). They cover:
  - visibility rules;
  - publishing, and rejection requiring a reason;
  - the company self-submission flow, including re-review after an edit and isolation between companies;
  - availability in all six cases;
  - validation of every vocabulary, price ranges, coverage areas and unknown sectors or needs;
  - checks when linking a company account to an organisation;
  - language codes on claims;
  - import create and update, and all-or-nothing import.
- **Frontend:** lint, type check and production build pass.
- **End to end:** a browser walkthrough as admin:
  - created an organisation and a solution with LGA coverage;
  - published it;
  - confirmed that filtering by Adamawa shows "operates in part of this area".
  - The test records were then deleted from the development database.

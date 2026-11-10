# Technology solutions directory

There is no open register of technology solutions for Nigeria (data gap
`directory.no_open_registry`). The directory therefore starts empty and is filled in three ways:

1. **Administrators** add organisations and solutions in the app (Directory → Add organisation).
2. **Companies** register their own organisation and submit solutions for review. An admin creates
   a *company* account; the company signs in, registers its organisation, adds solutions and
   submits them. Nothing a company enters is visible to others until an admin approves the
   organisation and publishes the solution. A company's later edits send the solution back for
   review.
3. **Batch import** of curated records from a YAML file:
   `connectly directory import path/to/file.yaml` (all or nothing; re-importing updates records
   matched by name).

Every organisation and solution records its source (`source_description`, optional
`source_url`) and a verification status: *not verified*, *checked against source*, *verified in
the field* or *disputed*. Every change is in the audit log.

## Fields

The brief's 20 company fields are all covered:

| Brief | Where |
| --- | --- |
| Company name, website, headquarters, industry | Organisation: `name`, `website`, `headquarters` + `headquarters_country` + `headquarters_state_id`, `industry`, `org_type` |
| Sector, product name, description | Solution: `sector`, `need_codes`, `name`, `summary`, `description`, `delivery_model` |
| Target beneficiaries | `beneficiary_groups` (fixed list) and `target_beneficiaries` (free text) |
| Pricing | `pricing_model`, `price_min_ngn`, `price_max_ngn`, `price_unit`, `pricing_notes` |
| Geographic coverage, expansion interests | `nationwide`, plus coverage by state, LGA or ward marked *operating* or *expansion interest* |
| Distribution requirements | `distribution_channels` (fixed list), `distribution_notes` |
| Internet, device requirements | `internet_requirement`, `device_requirement`, plus `power_requirement` and `literacy_requirement` |
| Languages, accessibility | `languages` (ISO 639), `accessibility_features`, `accessibility_notes` |
| Partnership opportunities | `partnership_types`, `partnership_notes` |
| Verification status, source, last updated | `verification_status`, `source_description`, `source_url`, `updated_at` |

Also: `implementation_notes` and `evidence_of_impact`.

Structured fields use the fixed vocabularies served at `GET /api/v1/directory/vocabularies`,
so matching compares like with like. **Empty means not known.** It is shown as "Not known" and
lowers match confidence; it is never filled in automatically.

## Import file format

```yaml
organisations:
  - name: Example Health Ltd           # matched case-insensitively on re-import
    org_type: startup                  # see vocabularies: org_types
    industry: Digital health
    website: https://example.org
    headquarters: Yola
    headquarters_country: NG
    headquarters_state: Adamawa        # state name (Nigeria only)
    status: active                     # active (default) or submitted
    source_description: Company website, retrieved 2026-11-10
    source_url: https://example.org/about
    solutions:
      - name: Example Clinic App
        status: draft                  # draft (default) or published
        sector: health
        need_codes: [health.telemedicine]
        summary: Remote consultations for primary health centres.
        internet_requirement: mobile_3g
        device_requirement: smartphone
        languages: [en, ha]
        nationwide: false
        coverage:
          - {state: Adamawa}                                   # whole state, operating
          - {state: Adamawa, lga: Yola North, kind: expansion_interest}
        source_description: Company website, retrieved 2026-11-10
        source_url: https://example.org/product
```

Only enter what the source states. Record prices and coverage as published, with the date
retrieved in `source_description`.

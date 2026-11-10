# Milestone 10: Reports, dashboard and administration

Completed 10 November 2026.

## What was built

- **Saved reports** (migration `0005`, `/api/v1/reports`). Every analysis can be saved as a report: intelligence brief, needs assessment, technology matching or market entry.
  - The server re-runs the analysis from its parameters rather than trusting the browser's copy.
  - It stores the result as a dated snapshot.
  - Users see their own reports; admins see all.
  - Creating and deleting reports is written to the audit log.
- **PDF export** (`connectly/reports/pdf.py`, ReportLab and svglib, both free and pure-Python).
  - Each page has the official logo, drawn from the unaltered SVG, a gold rule, and a footer with the report title, generation time and page number.
  - Findings keep their tags (fact, derived, recommendation, data gap), their evidence ids and an evidence table.
  - AI summaries are labelled as AI-generated.
- **Dashboard.** The overview is rebuilt from live counts:
  - an Adamawa panel: LGAs, wards, modelled population, facilities, settlements and claims, with links;
  - the four workflows;
  - national coverage, the directory, community claims and reports;
  - values loaded per sector;
  - open data gaps.
- **Administration hub** (`/admin`):
  - users, audit log and directory review queue;
  - datasets and gaps;
  - activity counts;
  - the record of dataset loads (`GET /api/v1/ingest/runs`).
- **Navigation.** The main menu is now Overview, Explorer, Intelligence, Needs, Matching, Market entry, Directory and Reports. Data sources moved to the account menu and the footer.

## Tests

- **Backend:** 152 tests pass (6 new). They cover:
  - saving and exporting a PDF for all four report kinds;
  - access control: other users cannot read, download or delete a report, and admins see all;
  - parameter validation.
- **Browser walkthrough:**
  - the dashboard on desktop and mobile;
  - saving a needs report and downloading its PDF;
  - the reports list;
  - the administration hub.
- The PDF layout was checked visually, including the logo.

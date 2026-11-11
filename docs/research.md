# Research intelligence (Gemini)

Research intelligence is a separate, optional service. It helps researchers find and record
evidence about technology access across Nigeria's 36 states and the FCT, in all eight
sectors. It uses the Google Gemini API on the **free tier only**.

It does not replace anything. Needs assessment, matching, market entry, profiles and the
deterministic brief sections never call Gemini, and work the same with or without a key. A
test (`test_engines_do_not_depend_on_gemini`) fails if those modules import the AI or research
code.

## What it does

| Step | Who | Gemini feature | What is kept |
| --- | --- | --- | --- |
| 1. Live web research | Researchers, admins | `gemini-2.5-flash` with Google Search grounding | **Nothing** but usage counts |
| 2. Analyse a source | Researchers, admins | Text model, structured output, no Search | The source record and findings that pass the checks |
| 3. Review findings | Researchers, admins | None | Status, note, reviewer, time; audit log entry |
| 4. Use findings | Everyone signed in | None | Findings appear in intelligence briefs and PDF reports, cited |
| Optional: brief summary | Anyone building a brief | Text model | Nothing (the summary is shown, and in a saved report) |

### 1. Live web research

A natural-language question, for example *"Identify communities in Northern Nigeria with
limited access to digital healthcare."*, with an optional scope (all of Nigeria, a
geopolitical zone, Northern or Southern Nigeria, or one state) and an optional sector.

Gemini searches the web with Google Search and answers. The page shows:

- the answer, labelled **AI-generated · Unverified · Not stored**;
- numbered markers after each passage Google reports as supported, linked to the sources;
- the sources found by Google Search;
- Google's **Search Suggestions**, displayed as provided (required by Google's terms), in a
  sandboxed frame;
- limitations: search results under-represent many rural communities, figures are as
  reported by each source, and sentences starting "Inference:" are the model's conclusions,
  not facts from a source.

The model is told to use only what the search returns, to give the year of every figure, to
mark its own conclusions as "Inference:", and to say plainly when the search finds nothing
reliable for a place. It is told never to estimate or invent numbers.

**Why the answer is not stored.** Google's Additional Terms for Grounding with Google Search
do not allow caching, storing or reusing Grounded Results or their links, and require them to
be shown only to the user who asked, with the Search Suggestions. So the answer, its sources
and its links are returned to the browser and not written to the database or the cache. The
`ai_usage` table records only that a request was made, its outcome, tokens and number of
search queries. A test checks that no answer text or link reaches the database.

To keep evidence, open a source and submit the page's own address under step 2.

### 2. Analyse a source

A researcher submits the web address of a public page or PDF they have opened and chosen.
Google Search redirect links (`vertexaisearch.cloud.google.com`) are refused with an
explanation.

1. Connectly fetches the page itself (`connectly/research/fetch.py`): http(s) only; no
   private, local or reserved addresses, including after each redirect; at most 8 MB; HTML,
   plain text or PDF.
2. It records the title, publisher, publication date and how that date was found (page
   metadata, structured data, a single `<time>` element, PDF creation date, or a date the
   document states, read by AI), the retrieval time and a SHA-256 of the text.
3. Gemini, without Search, extracts up to 15 findings as structured JSON. Each has a plain
   statement, a **verbatim quote** from the document, what the source presents it as
   (measured, estimate, assumption, opinion), the sector, the period and the places named.
4. Each finding is checked before it is stored:
   - the quote must appear word for word in the document (after normalising whitespace and
     curly quotes);
   - every number in the statement must appear in the quote;
   - at least one place must match a loaded state, LGA or ward, or a geopolitical zone (stored
     as its states). An LGA or ward name that exists in several states counts only if the
     finding also names the state;
   - no personal contact details.

   Findings that fail are listed with the reason and not stored.
5. Stored findings start **unverified**, with `extracted_by = gemini:<model>`: the statement is
   the model's wording; the quote is the source's own words.

Extractions are cached for 30 days (`CONNECTLY_GEMINI_CACHE_DAYS`), keyed by the model, the
prompt version, the document's hash, the sector and the focus question. Analysing the same
unchanged document again does not call Gemini. This is allowed: step 2 does not use
Grounding with Google Search, and the document was fetched by Connectly from an address the
researcher chose.

### 3. Review

A researcher or administrator marks a finding **source verified**, **disputed**, **retired**
or back to **unverified**, and must say what they checked. Each review is in the audit log.

### 4. Use in briefs and reports

Intelligence briefs have a **Research findings from sources** section. Findings about the
area, a larger area that contains it, or an area inside it are included (disputed and retired
ones are not). Each is an evidence item with:

- the statement and the quoted passage;
- the source title, publisher, URL, publication date and retrieval date;
- the value type from what the source presents (an opinion is recorded as an assumption, not a
  measurement) and the verification status;
- "Unverified:" in front of the statement, and a note in the section, until it is reviewed.

Only reviewed (source-verified) findings count towards the brief having enough evidence for an
AI summary. The summary check (`docs/ai.md`) applies to them like any other evidence.

## Information types, as shown to users

| Label | Meaning |
| --- | --- |
| Measured / Estimate / Assumption (per source) | What the source presents, quoted |
| Opinion or recommendation | A view stated in the source |
| Unverified | Extracted by AI; quote matched to the source; no person has confirmed it |
| Source verified | A researcher checked it against the source |
| AI-generated | A live answer or brief summary written by Gemini |
| Inference | A conclusion the model drew, not a fact from a source |
| Recommendation | Produced by Connectly's own rules (briefs, matching, market entry) |

## Free tier only: what was checked, and how Connectly enforces it

Checked against Google's documentation on 11 November 2026:

- Google Search grounding is available on the free tier for Gemini 2.5 Flash and Gemini 2.5
  Flash-Lite (pricing page). Newer Flash models are free for text, but grounding on them is
  listed for the paid tier only.
- The free tier has request-per-minute, token-per-minute and request-per-day limits, per
  Google Cloud project; daily limits reset at midnight Pacific time. The current numbers are
  shown in AI Studio and are not guaranteed (rate limits page).
- A project moves to a paid tier only when a billing account is linked and prepaid credit is
  bought (billing page). A key from a project with no billing account is not charged.
- Free-tier prompts and answers may be used by Google to improve its products and may be
  reviewed by people; Google asks that no sensitive, confidential or personal information be
  sent (pricing page and terms). Nigeria is an available region. The free tier is not offered
  in the EEA, the UK or Switzerland.
- `generateContent` remains supported; Gemini 2.5 models are not deprecated (deprecations
  page, updated 22 October 2026).

What the code does (`connectly/ai/gemini.py`):

1. **Model allow-list.** Web research may use only `gemini-2.5-flash` or
   `gemini-2.5-flash-lite`. Text tasks may also use `gemini-3.5-flash` and
   `gemini-3.1-flash-lite`. Any other configured model is refused before a request is made.
2. **Own limits, below Google's.** Default 200 web searches and 200 other requests per Pacific
   day, and 5 requests per minute. Checked under a database lock, so several API workers share
   one budget.
3. **Google's limit.** A 429 `RESOURCE_EXHAUSTED` reply stops all calls until the reset:
   midnight Pacific for a daily quota, otherwise the `retryDelay` Google gives (at least 10
   seconds). Users are told nothing was charged and when requests resume.
4. **Accounting.** Every attempt is recorded in `ai_usage`, including those stopped locally:
   purpose, model, outcome, HTTP status, tokens, search queries, time taken and errors (with
   the key removed). Administrators see it under Administration → AI usage.
5. **Caching.** Source extractions only (see above). Live answers are never cached.
6. **No personal data.** Questions, focus text and review notes containing phone numbers,
   email addresses or ID numbers are refused. The page reminds users not to enter personal or
   confidential information.
7. **The key** is read from `CONNECTLY_GEMINI_API_KEY`, sent in the `x-goog-api-key` header
   (never in a URL), never logged, never returned to the browser.

**Your part:** create the key in [Google AI Studio](https://aistudio.google.com/apikey) in a
Google Cloud project that has **no billing account linked**, and do not link one. Connectly
cannot see a project's billing status.

## Setting it up

```bash
# backend/.env (or .env for Docker)
CONNECTLY_GEMINI_API_KEY=your-key
# optional: brief summaries with Gemini as well
CONNECTLY_AI_PROVIDER=gemini
```

Restart the API. The Research page shows the free-tier status and today's usage.

| Variable | Default |
| --- | --- |
| `CONNECTLY_GEMINI_API_KEY` | none (research off) |
| `CONNECTLY_GEMINI_SEARCH_MODEL` | `gemini-2.5-flash` |
| `CONNECTLY_GEMINI_TEXT_MODEL` | `gemini-2.5-flash` |
| `CONNECTLY_GEMINI_DAILY_SEARCH_LIMIT` | `200` |
| `CONNECTLY_GEMINI_DAILY_REQUEST_LIMIT` | `200` |
| `CONNECTLY_GEMINI_PER_MINUTE_LIMIT` | `5` |
| `CONNECTLY_GEMINI_TIMEOUT` | `90` seconds |
| `CONNECTLY_GEMINI_CACHE_DAYS` | `30` |

## API

All under `/api/v1/research`, signed in.

| Method and path | Role | Purpose |
| --- | --- | --- |
| `GET /status` | any | Configured or not, models, today's usage, notices |
| `GET /zones` | any | Geopolitical zones and northern/southern groups, with loaded states |
| `POST /live` | researcher, admin | Live web research (not stored) |
| `POST /sources` | researcher, admin | Fetch a page or PDF and extract checked findings |
| `GET /findings` | any | Filter by `area_id`, `sector`, `status` |
| `POST /findings/{id}/review` | researcher, admin | Set status with a note |
| `GET /usage` | admin | Usage by day, purpose and outcome; recent errors |

Errors: 503 not configured, 409 model not on the free-tier list, 429 a limit was reached
(Connectly's or Google's), 422 invalid input or a source that cannot be read, 502 other
Gemini errors.

## Limits of this service

- Web search coverage of rural Nigeria is thin; an answer that finds little is not evidence
  that a community is well served.
- The quote check proves the passage is in the source, not that the statement reads it
  correctly. That is why findings start unverified.
- Place matching uses loaded boundaries and aliases. Settlement names are not matched yet;
  they are kept as written in the finding.
- Google's free-tier limits can change without notice. Connectly's own limits are settings,
  so they can be lowered.

## What was and was not tested here

This workspace cannot reach `generativelanguage.googleapis.com`. Every Gemini call in the tests
goes to a stand-in that replies in the documented `generateContent` format. The tests
(`backend/tests/test_research.py`, 23 tests) cover the model allow-list, local limits, daily
and per-minute 429 handling, key scrubbing, that live answers leave nothing in the database,
the quote and number checks, place and zone matching, caching, URL safety (private addresses,
redirects, Google redirect links), page metadata, review permissions and the audit log, briefs
with findings, and that the engines do not import Gemini. The Research and AI usage pages were
checked in a browser against a local stand-in server.

Run one live question and one source analysis after setting the key, and check the AI usage
page.

## Sources

- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Billing: https://ai.google.dev/gemini-api/docs/billing
- Rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Grounding with Google Search: https://ai.google.dev/gemini-api/docs/generate-content/google-search
- Interactions API migration (generateContent remains supported):
  https://ai.google.dev/gemini-api/docs/migrate-to-interactions
- Deprecations: https://ai.google.dev/gemini-api/docs/deprecations
- Available regions: https://ai.google.dev/gemini-api/docs/available-regions
- Gemini API Additional Terms of Service: https://ai.google.dev/gemini-api/terms. This page
  could not be fetched from the build workspace; the grounding rules above were read from a
  copy of the terms dated 20 May 2025. Re-read the current terms before production use.

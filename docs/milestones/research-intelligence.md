# Research intelligence with Gemini, 11 November 2026

## Objective

Add Google Gemini (free tier) as the AI provider for research: natural-language research across
all eight sectors and all 36 states and the FCT, evidence stored with sources and dates,
evidence-backed briefs with citations, and a clear distinction between verified information,
estimates, assumptions and AI output. Free tier only, no unexpected charges, usage tracked,
caching, graceful quota handling, and the deterministic engines kept independent.

## Checked before implementation

Google's documentation was read on 11 November 2026 (links in `docs/research.md`):

| Question | Finding | Effect on the design |
| --- | --- | --- |
| Is Google Search grounding free? | Yes on Gemini 2.5 Flash and Flash-Lite (shared daily allowance). Newer Flash models: free for text, grounding paid only. | Web research is restricted to the two 2.5 models. |
| Limits | Per project; per minute and per day; daily reset at midnight Pacific; numbers shown in AI Studio, not guaranteed. | Connectly keeps its own lower limits, counted in Pacific days. |
| How charges start | Only after a billing account is linked and credit prepaid. | Documented: use a project with no billing. Paid-only models are refused in code. |
| Data use | Free-tier content may improve Google's products and be reviewed by people; do not send sensitive or personal information. | Warning on the page; personal-data guard on every input. |
| Storing grounded results | The Additional Terms forbid caching or storing Grounded Results and Links, and require Search Suggestions to be shown. | Live answers are never stored or cached. Evidence is kept only from sources researchers submit and Connectly fetches itself. |
| API | `generateContent` remains supported; 2.5 models not deprecated. | REST `generateContent` with `x-goog-api-key`. |

**One conflict with the request.** The request asked to store findings and source URLs from
research. Google's terms do not allow storing what Search grounding returns. The design keeps
both goals legal: the live answer is shown and discarded, and anything worth keeping is
re-obtained from the original source, fetched by Connectly, with a verbatim quote checked
against it. The current terms page could not be fetched from the workspace; the terms were read
from a copy dated 20 May 2025, and should be re-read before production use.

## What was built

| Part | Files |
| --- | --- |
| Settings (`CONNECTLY_GEMINI_*`) | `core/config.py`, `.env.example` files, `docker-compose.yml` |
| Gemini client: allow-list, limits, 429 handling, accounting, key scrubbing | `ai/gemini.py` |
| Tables `ai_usage`, `ai_cache`, `research_source`, `research_finding`, `research_finding_area` | `models/research.py`, migration `0006` |
| Safe fetching of pages and PDFs (`pypdf`, BSD licence) | `research/fetch.py` |
| Live research, source analysis with quote and number checks, place and zone matching, findings, review | `research/service.py`, `taxonomy/zones.yaml` |
| API `/api/v1/research/*` | `api/routers/research.py` |
| Findings in briefs and PDF reports | `ai/brief.py`, `reports/pdf.py` |
| Gemini as the optional brief summary model | `ai/providers.py` |
| Research page, AI usage page, nav link | `frontend/src/app/(app)/research`, `(app)/admin/ai-usage`, `components/research/Research.tsx` |

## Tests

- `backend/tests/test_research.py`: 23 tests, all Gemini traffic to a stand-in in Google's
  documented response format. Backend total: 186 passed. `alembic check` clean.
- Frontend lint, type check, unit tests, build: pass.
- Browser tests: 8 passed. They now check the research section in briefs, the Research page
  without a key, and the AI usage page.
- The Research and AI usage pages were also exercised in a browser with the API pointed at a
  local stand-in server: answer with source markers, sources, Search Suggestions in the
  sandboxed frame (links open in a new tab), usage counts, mobile width without horizontal
  scrolling.

## Not verified here

The workspace cannot reach `generativelanguage.googleapis.com`, so no real Gemini request was
made. Set a key and run one live question and one source analysis (see `docs/research.md`).
